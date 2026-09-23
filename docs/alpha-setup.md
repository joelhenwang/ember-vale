# Private-alpha setup script (unfamiliar tester)

Goal: from a clean checkout to a played story in under 30 minutes, with
no prior project knowledge. Read nothing else first; report anything
that contradicts these steps verbatim.

## 1. Prerequisites

- Node 20+, Docker with compose, a Chromium browser (or Edge).
- No API keys needed for the scripted path. Narration is deterministic
  fake text until a live key is set (see §7) — judge flow, not prose.

## 2. Start the stack

```bash
git clone https://github.com/joelhenwang/ember-vale.git ember-vale && cd ember-vale
cp .env.example .env
# Fill WORLDSIM_SECURITY__API_KEY with any long random string.
docker compose up -d
curl http://localhost:8101/api/v1/health/live     # {"status":"ok"}
curl http://localhost:8101/api/v1/health/ready    # status ready/degraded
npm install
npm run dev                                        # UI at http://localhost:5173
```

Stop here and report if any command fails, including the exact output.

Notes: the first `docker compose up` builds the API image and can take
several minutes with no output — let it finish.

If compose reports a port already allocated (5433, 8101, or 5173),
another stack is running on this machine. Identify it first, and never
stop a process you cannot identify:

```bash
docker ps --format '{{.Names}} {{.Ports}}'
```

- If you recognize the owner as a disposable stack (for example a
  previous checkout of this repo), stop it from its own directory with
  `docker compose down`, then rerun `docker compose up -d` here.
- Otherwise keep it and run this checkout on alternate ports, then
  point the dev proxy at the alternate API port:
  ```bash
  export POSTGRES_PORT=55433 API_PORT=18101   # PowerShell: $env:POSTGRES_PORT='55433'; $env:API_PORT='18101'
  docker compose up -d
  ```
  In `vite.config.ts` change the proxy target from
  `http://localhost:8101` to `http://localhost:18101`, and use port
  18101 in the health curls above.

## 3. First story (observer, ~10 minutes)

1. Open the UI. On the home screen press **Begin a new tale**.
2. Step 1: pick **Ember Vale**. Step 2: add **Wren** and **Ash**.
3. Step 3: choose **Observer**. Step 4: title it however you like.
4. Continue to Review, then **Begin the story**.
5. On the play page: press **Start journey**, then **Commit beat** twice.
6. Reload the page: the same story continues with its history intact.
7. Go back Home: the story is featured there.

## 4. Optional: direct the story (~5 minutes)

The direction panel appears only after taking a Director or God seat —
observers never see it, so this is a separate exercise.

1. On the play page, in the **Operating seat** card, press
   **Take the Director seat**. A **Direct the story** card appears.
2. Type "Ash heads to the Market" and press **File direction**.
3. If the direction comes back asking for clarification, edit the text
   to name characters and places explicitly and resubmit.
4. Commit a beat and check the outcome matches what was filed.

## 5. Report back

- Time taken per step above, and any step where you hesitated.
- Anything that looked broken, fake, or confusing (placeholder art is
  expected; the Settings connection tests are timer-faked).
- Whether beats, the journey, reload/resume, and (if tried) direction
  filing behaved as the words on screen said they would.

## 6. Evidence status

An automated smoke test on a fresh clone (alternate ports) already
drove the observer path end to end via Quick Start: it proves a clean
install reaches playable Observer mode. It does not prove the manual
wizard above (§3) is clear to a newcomer — that is what this session
establishes. Record hesitations verbatim; they are the finding.

## 7. Live narration (maintainer only)

```bash
# in .env, then: docker compose up -d --force-recreate api
WORLDSIM_PROVIDER__ACTIVE_PROFILE=openrouter
WORLDSIM_PROVIDER__OPENROUTER_API_KEY=<key>
```

Replay §3 and judge the prose: scene continuity across beats, cast
voice consistency, and whether travel/actions resolve as narrated.
