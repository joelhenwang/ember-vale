# Private-alpha setup script (unfamiliar tester)

Goal: from a clean checkout to a played story in under 30 minutes, with
no prior project knowledge. Read nothing else first; report anything
that contradicts these steps verbatim.

## 1. Prerequisites

- Node 20+, Docker with compose, a Chromium browser (or Edge).
- No API keys needed for the scripted path. Narration is deterministic
  fake text until a live key is set (see §5) — judge flow, not prose.

## 2. Start the stack

```bash
git clone <repo> ember-vale && cd ember-vale
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
several minutes with no output — let it finish. If compose reports a
port already allocated (5433, 8101, or 5173), another stack is running
on this machine; stop it before continuing.

## 3. First story (observer, ~10 minutes)

1. Open the UI. On the home screen press **Begin a new tale**.
2. Step 1: pick **Ember Vale**. Step 2: add **Wren** and **Ash**.
3. Step 3: choose **Observer**. Step 4: title it however you like.
4. Continue to Review, then **Begin the story**.
5. On the play page: press **Start journey**, then **Commit beat** twice.
6. File a direction: type "Ash heads to the Market" and submit it.

## 4. Report back

- Time taken per step above, and any step where you hesitated.
- Anything that looked broken, fake, or confusing (placeholder art is
  expected; the Settings connection tests are timer-faked).
- Whether beats, the direction filing, and the journey behaved as the
  words on screen said they would.

## 5. Live narration (maintainer only)

```bash
# in .env, then: docker compose up -d --force-recreate api
WORLDSIM_PROVIDER__ACTIVE_PROFILE=openrouter
WORLDSIM_PROVIDER__OPENROUTER_API_KEY=<key>
```

Replay §3 and judge the prose: scene continuity across beats, cast
voice consistency, and whether travel/actions resolve as narrated.
