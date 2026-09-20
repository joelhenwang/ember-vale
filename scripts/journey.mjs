#!/usr/bin/env node
/**
 * Deterministic end-to-end journey against the deployed stack (Stage D).
 *
 * Drives the real HTTP API the same way the UI does: presets -> draft ->
 * atomic create -> idempotent replay -> travel action -> committed beat ->
 * fresh reads -> same-beat retry -> setup provenance. No mocks, no timers.
 *
 * Usage:
 *   EMBER_VALE_API_KEY=<operator key> node scripts/journey.mjs \
 *     [--api http://localhost:8101/api/v1] [--title "My journey"]
 *
 * Exit 0 prints a JSON summary; any failed expectation throws.
 */

const args = process.argv.slice(2);
const opt = (name, fallback) => {
  const i = args.indexOf(name);
  return i >= 0 && args[i + 1] ? args[i + 1] : fallback;
};

const API = opt('--api', 'http://localhost:8101/api/v1');
const TITLE = opt('--title', 'Scripted journey');
const KEY = process.env.EMBER_VALE_API_KEY || process.env.WORLDSIM_SECURITY__API_KEY || '';
if (!KEY) throw new Error('set EMBER_VALE_API_KEY (the compose operator key)');

const RUN = Date.now().toString(36);
const headers = (extra = {}) => ({
  'Content-Type': 'application/json',
  Authorization: `Bearer ${KEY}`,
  'X-Worldsim-Role': 'watcher',
  ...extra,
});

async function call(method, path, body, extraHeaders) {
  const res = await fetch(API + path, {
    method,
    headers: headers(extraHeaders),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  let json = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    throw new Error(`${method} ${path} -> ${res.status} (non-JSON): ${text.slice(0, 200)}`);
  }
  if (!res.ok) {
    throw new Error(
      `${method} ${path} -> ${res.status}: ${(json?.error?.code ?? '') + ' ' + (json?.error?.message ?? text).slice(0, 200)}`
    );
  }
  return json;
}

const expect = (cond, message) => {
  if (!cond) throw new Error(`EXPECT: ${message}`);
};

// 1. Presets: corrected starter revision with both directed legs.
const presets = await call('GET', '/library/presets?kind=world');
const emberVale = presets.find((p) => p.name === 'Ember Vale');
expect(emberVale, 'Ember Vale preset listed');
const world = await call(
  'GET',
  `/library/presets/${emberVale.id}?revision=${emberVale.current_revision}`
);
expect(emberVale.current_revision === 2, `world current_revision is 2 (got ${emberVale.current_revision})`);
const legs = new Set(world.revision.travel.map((pair) => pair.join('>')));
expect(legs.has('hearth>market') && legs.has('market>hearth'), 'both directed legs published');

const chars = await call('GET', '/library/presets?kind=character');
const wren = chars.find((p) => p.name === 'Wren');
const ash = chars.find((p) => p.name === 'Ash');
expect(wren && ash, 'Wren and Ash presets listed');

// 2. Draft + atomic create + same-key replay.
const draft = await call('POST', '/story-drafts', {
  payload: {
    world: { preset_id: emberVale.id, preset_revision: emberVale.current_revision },
    cast: [
      {
        instance_key: 'wren',
        preset_id: wren.id,
        preset_revision: wren.current_revision,
        name: 'Wren',
        location_key: 'hearth',
      },
      {
        instance_key: 'ash',
        preset_id: ash.id,
        preset_revision: ash.current_revision,
        name: 'Ash',
        location_key: 'market',
      },
    ],
    mode: { role: 'watcher' },
    story: { title: `${TITLE} ${RUN}` },
    ai: { art_source: 'curated' },
  },
  current_step: 'review',
});
const createKey = `journey-${RUN}`;
const created = await call(
  'POST',
  '/stories',
  { draft_id: draft.id, expected_draft_version: 1 },
  { 'Idempotency-Key': createKey }
);
expect(created.replayed === false, 'first create is not a replay');
const wid = created.world_id;
const replayed = await call(
  'POST',
  '/stories',
  { draft_id: draft.id, expected_draft_version: 1 },
  { 'Idempotency-Key': createKey }
);
expect(replayed.replayed === true && replayed.world_id === wid, 'same key replays the same story');

// 3. Resolve runtime ids; verify starting places.
const map0 = await call('GET', `/stage2/map?world_id=${wid}`);
const byName = Object.fromEntries(map0.places.map((p) => [p.name, p]));
expect(byName.Hearth && byName.Market, 'Hearth and Market on the map');
expect(byName.Hearth.occupants.includes('Wren'), 'Wren starts at Hearth');
const hearthRoutes = (byName.Hearth.routes ?? []).map((r) => r.to_location_id);
expect(hearthRoutes.includes(byName.Market.id), 'map draws Hearth -> Market');
const wrenId = byName.Hearth.occupant_ids[byName.Hearth.occupants.indexOf('Wren')];

// 4. Travel action, then one committed beat.
const activity = await call('POST', '/stage2/activities', {
  world_id: wid,
  character_id: wrenId,
  kind: 'travel',
  to_location_id: byName.Market.id,
});
expect(activity.status === 'active', 'travel activity starts active');
const detail0 = await call('GET', `/stories/${wid}`);
const advanced = await call('POST', '/stage1/advance', {
  world_id: wid,
  absolute_index: detail0.absolute_index + 1,
});
expect(advanced.duplicate !== true, 'first advance commits (not a replay)');

// 5. Fresh reads: movement committed, chronicle agrees.
const map1 = await call('GET', `/stage2/map?world_id=${wid}`);
const market1 = map1.places.find((p) => p.name === 'Market');
expect(market1.occupants.includes('Wren'), 'Wren is in Market after the beat');
const timeline = await call('GET', `/stage2/timeline?world_id=${wid}&after=0&limit=20`);
expect(
  timeline.entries.some((e) => e.event_type === 'action_resolved'),
  'timeline records the resolved action'
);
const eventsBefore = timeline.entries.length;

// 6. Same-beat retry changes nothing; setup provenance is stable.
const retry = await call('POST', '/stage1/advance', {
  world_id: wid,
  absolute_index: detail0.absolute_index + 1,
});
expect(retry.duplicate === true, 'same beat replays as duplicate');
const timeline2 = await call('GET', `/stage2/timeline?world_id=${wid}&after=0&limit=20`);
expect(timeline2.entries.length === eventsBefore, 'retry adds no events');
const setup = await call('GET', `/stories/${wid}/setup`);
expect(setup.provenance === 'created', 'setup provenance is created');

console.log(
  JSON.stringify(
    {
      ok: true,
      api: API,
      world_id: wid,
      title: `${TITLE} ${RUN}`,
      world_revision: emberVale.current_revision,
      advance_cursor: advanced.absolute_index,
      events: eventsBefore,
      setup_hash: setup.content_hash.slice(0, 12),
    },
    null,
    2
  )
);
