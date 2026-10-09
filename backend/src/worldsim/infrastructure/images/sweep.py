"""Delete stored picture files that no asset row refers to any more.

Going back to a turn removes the pictures of removed scenes with their
jobs and asset rows but never their files: a branch may show the same file
through its own row (branches share files by ``content_ref``). A painting
that finishes after its job was removed leaves a file nobody refers to as
well. This sweep finds such files and deletes them.

What it looks at: only files under ``<assets>/generated`` (the starter art
in ``revamp/`` and anything else is never touched). A file is in use when
any ``asset_record`` row, in any story, branch or the library, has it as
its ``content_ref`` (compared without case, so a doubtful match keeps
it). A picture variant (``generated/.variants/<asset id>-w<width>.webp``)
is in use while its asset row exists.

What makes it careful:

* a file younger than the grace (default 1 hour) stays: a job or upload
  may be writing it right now, before its row is committed;
* a file goes only when it was already unused at the previous sweep of
  this process (6 hours earlier by default), so the first sweep after a
  start deletes nothing, and a backup taken between a rewind and the sweep
  still holds every file its database dump refers to;
* the database is read after the folder is listed, so a row added while
  listing still protects its file (and its file is young anyway);
* no rows at all while files exist (an empty or wrong database) deletes
  nothing;
* symlinks are never followed nor deleted, and a path that resolves
  outside the folder is skipped.

Failures are logged and never stop the API or the worker.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from worldsim.application.unit_of_work import UnitOfWork

_log = logging.getLogger(__name__)

GENERATED = "generated"
VARIANTS = "generated/.variants"
_VARIANT = re.compile(r"^([0-9a-f]{32})-w\d+\.webp$")


@dataclass
class StoredFile:
    ref: str  # relative to the assets root, with forward slashes
    size: int
    mtime: float


@dataclass
class SweepReport:
    files: int = 0
    in_use: int = 0
    young: int = 0
    #: Unused and old enough, but not unused at the previous sweep yet.
    waiting: int = 0
    deleted: int = 0
    bytes_freed: int = 0
    failed: int = 0
    refused: str = ""
    #: Unused and older than the grace (what a dry run would delete).
    unused: list[StoredFile] = field(default_factory=list[StoredFile])

    @property
    def unused_bytes(self) -> int:
        return sum(f.size for f in self.unused)


def list_generated(root: Path) -> list[StoredFile]:
    """Every regular file under ``root/generated`` (symlinks left out)."""
    base = root / GENERATED
    found: list[StoredFile] = []
    if not base.is_dir():
        return found
    for folder, dirs, names in os.walk(base, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(folder) / d).is_symlink()]
        for name in names:
            path = Path(folder) / name
            try:
                stat = path.lstat()
            except OSError:
                continue
            if path.is_symlink() or not path.is_file():
                continue
            ref = path.relative_to(root).as_posix()
            found.append(StoredFile(ref=ref, size=stat.st_size, mtime=stat.st_mtime))
    return found


def _norm(ref: str) -> str:
    return ref.replace("\\", "/").removeprefix("./").casefold()


def in_use(file: StoredFile, refs: set[str], asset_ids: set[UUID]) -> bool:
    """True when some asset row still needs this file."""
    if _norm(file.ref) in refs:
        return True
    folder, _, name = file.ref.rpartition("/")
    if folder == VARIANTS:
        match = _VARIANT.match(name)
        return match is not None and UUID(match.group(1)) in asset_ids
    return False


class PictureSweeper:
    """Deletes unused picture files, every few hours, from the background loops."""

    def __init__(
        self,
        factory: Callable[[], UnitOfWork],
        assets_root: Path,
        *,
        every_s: float = 6 * 3600,
        grace_s: float = 3600,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._factory = factory
        self._root = assets_root.resolve()
        self._every_s = every_s
        self._grace_s = grace_s
        self._clock = clock
        #: Files found unused (and old enough) by the previous sweep.
        self._unused_before: set[str] = set()
        self._stopping = asyncio.Event()

    async def survey(self) -> SweepReport:
        """What is in use and what is not; deletes nothing."""
        files = await asyncio.to_thread(list_generated, self._root)
        async with self._factory() as uow:
            rows = await uow.assets.stored_refs()
        report = SweepReport(files=len(files))
        if files and not rows:
            report.refused = "no asset rows at all: the database may be empty or the wrong one"
            return report
        refs = {_norm(ref) for _, ref in rows}
        ids = {asset_id for asset_id, _ in rows}
        now = self._clock()
        for file in files:
            if in_use(file, refs, ids):
                report.in_use += 1
            elif now - file.mtime < self._grace_s:
                report.young += 1
            else:
                report.unused.append(file)
        return report

    async def sweep_once(self) -> SweepReport:
        report = await self.survey()
        if report.refused:
            _log.warning("picture sweep deleted nothing: %s", report.refused)
            self._unused_before = set()
            return report
        due = [f for f in report.unused if f.ref in self._unused_before]
        report.waiting = len(report.unused) - len(due)
        self._unused_before = {f.ref for f in report.unused}
        for file in due:
            if await asyncio.to_thread(self._delete, file.ref):
                report.deleted += 1
                report.bytes_freed += file.size
                self._unused_before.discard(file.ref)
            else:
                report.failed += 1
        _log.info(
            "picture sweep: %d files, %d in use, %d young, %d waiting a sweep, "
            "%d deleted (%.1f MB freed), %d failed",
            report.files,
            report.in_use,
            report.young,
            report.waiting,
            report.deleted,
            report.bytes_freed / 1e6,
            report.failed,
        )
        return report

    def _delete(self, ref: str) -> bool:
        base = self._root / GENERATED
        path = self._root / ref
        try:
            if path.is_symlink() or base not in path.resolve().parents:
                return False
            path.unlink()
        except FileNotFoundError:
            return True  # another process swept it first
        except OSError as exc:
            _log.warning("picture sweep could not delete %s: %s", ref, exc)
            return False
        return True

    async def run_forever(self) -> None:
        while not self._stopping.is_set():
            try:
                await self.sweep_once()
            except Exception:  # never break the loops over a sweep
                _log.exception("picture sweep failed")
            try:
                await asyncio.wait_for(self._stopping.wait(), self._every_s)
            except TimeoutError:
                pass

    async def stop(self) -> None:
        self._stopping.set()
