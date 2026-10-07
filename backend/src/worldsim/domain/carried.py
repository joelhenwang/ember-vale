"""What a character carries, from the studio's appearance text.

The library studio keeps a character's look as "Key: value" lines, one of
them "Carries: a tide-knife, a coil of line and her grandmother's bell".
A story made with that character starts with each of those as an item it
holds, so the satchel, the narrator and the decisions all know of them.
"""

from __future__ import annotations

import re

#: The appearance lines the studio writes (domain-side copy of the form's keys).
_KEYS = (
    "Age",
    "Race",
    "Sex",
    "Hair",
    "Eyes",
    "Height",
    "Build",
    "Marks",
    "Wears",
    "Carries",
    "Condition",
)
#: A story starts with at most this many carried things per character.
MAX_CARRIED = 8
_ITEM_CHARS = 60
_LEADING = re.compile(r"^(?:and|a|an|the|some|her|his|their|its|my|your)\s+", re.IGNORECASE)


def _carries_line(appearance: str) -> str:
    found: list[str] = []
    inside = False
    for line in appearance.splitlines():
        key = next((k for k in _KEYS if line.startswith(f"{k}:")), None)
        if key is not None:
            inside = key == "Carries"
            if inside:
                found.append(line[len("Carries:") :])
        elif inside:
            found.append(line)
    return " ".join(part.strip() for part in found).strip()


def carried_items(appearance: str | None) -> list[str]:
    """The things named on the "Carries:" line, each a short item name."""
    line = _carries_line(appearance or "")
    if not line:
        return []
    line = line.rstrip(".").replace(" and ", ", ")
    names: list[str] = []
    seen: set[str] = set()
    for raw in re.split(r"[,;]", line):
        name = raw.strip()
        while (stripped := _LEADING.sub("", name)) != name:
            name = stripped
        name = name.strip(" .")[:_ITEM_CHARS].strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        names.append(name[0].upper() + name[1:])
        if len(names) == MAX_CARRIED:
            break
    return names
