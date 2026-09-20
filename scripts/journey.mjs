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
 *     [--api http://localhost:8101/api/v1] [--title "My journey"] [--artifact .journey-artifact.json]
 *   EMBER_VALE_API_KEY=<operator key> node scripts/journey.mjs --resume [--artifact .journey-artifact.json]
 *
 * Create mode drives presets -> draft -> create -> travel -> beat and writes
 * a resume artifact (story id, clock, actor location, event cursor).
 * Resume mode (after restarting the API *without* resetting the database)
 * asserts the same story resumes, continues it, then creates a second story
 * and proves B's beat adds nothing to A.
 *
 * Exit 0 prints a JSON summary; any failed expectation throws.
 */

import fs from 'node:fs';

const args = process.argv.slice(2);
const opt = (name, fallback) => {
  const i = args.indexOf(name);
  return i >= 0 && args[i + 1] ? args[i + 1] : fallback;
};

const API = opt('--api', 'http://localhost:8101/api/v1');
const TITLE = opt('--title', 'Scripted journey');
const ARTIFACT = opt('--artifact', '.journey-artifact.json');
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

async function makeStory(title, emberVale, wren, ash) {
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
      story: { title },
      ai: { art_source: 'curated' },
    },
    current_step: 'review',
  });
  const created = await call(
    'POST',
    '/stories',
    { draft_id: draft.id, expected_draft_version: 1 },
    { 'Idempotency-Key': `journey-${RUN}-${title.length}` }
  );
  return created.world_id;
}

if (args.includes('--resume')) {
  const artifact = JSON.parse(fs.readFileSync(ARTIFACT, 'utf8'));
  const wid = artifact.world_id;
  const detail = await call('GET', `/stories/${wid}`);
  expect(
    detail.absolute_index === artifact.absolute_index,
    `resumed clock ${detail.absolute_index} matches artifact ${artifact.absolute_index}`
  );
  const rmap = await call('GET', `/stage2/map?world_id=${wid}`);
  const place = rmap.places.find((p) => p.name === artifact.actor_location_place);
  expect(place && place.occupants.includes(artifact.actor), `${artifact.actor} still in ${artifact.actor_location_place}`);
  const rtl = await call('GET', `/stage2/timeline?world_id=${wid}&after=0&limit=50`);
  expect(
    rtl.entries.length === artifact.events,
    `resumed event cursor ${rtl.entries.length} matches artifact ${artifact.events}`
  );
  const continued = await call('POST', '/stage1/advance', {
    world_id: wid,
    absolute_index: detail.absolute_index + 1,
  });
  expect(continued.duplicate !== true, 'resume continue commits a new beat');
  const grown = await call('GET', `/stage2/timeline?world_id=${wid}&after=0&limit=50`);
  expect(grown.entries.length > rtl.entries.length, 'continued beat adds events to A');

  const rpresets = await call('GET', '/library/presets?kind=world');
  const remberVale = rpresets.find((p) => p.name === 'Ember Vale');
  const rchars = await call('GET', '/library/presets?kind=character');
  const bw = await makeStory(
    `${TITLE} B ${RUN}`,
    remberVale,
    rchars.find((p) => p.name === 'Wren'),
    rchars.find((p) => p.name === 'Ash')
  );
  const bdetail = await call('GET', `/stories/${bw}`);
  await call('POST', '/stage1/advance', {
    world_id: bw,
    absolute_index: bdetail.absolute_index + 1,
  });
  const afterB = await call('GET', `/stage2/timeline?world_id=${wid}&after=0&limit=50`);
  expect(
    afterB.entries.length === grown.entries.length,
    `B's beat adds nothing to A (${afterB.entries.length} vs ${grown.entries.length})`
  );
  fs.writeFileSync(
    ARTIFACT,
    JSON.stringify(
      {
        world_id: wid,
        title: artifact.title,
        absolute_index: continued.absolute_index,
        actor: artifact.actor,
        actor_location_place: artifact.actor_location_place,
        events: grown.entries.length,
      },
      null,
      2
    )
  );
  console.log(JSON.stringify({ ok: true, mode: 'resume', world_id: wid, second_story: bw }, null, 2));
  process.exit(0);
}

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
// The frontend omits player_intents when there are none because the backend
// rejects explicit null for this optional-but-not-nullable field.
const nullProbe = await fetch(API + '/stage1/advance', {
  method: 'POST',
  headers: headers(),
  body: JSON.stringify({
    world_id: wid,
    absolute_index: detail0.absolute_index + 1,
    player_intents: null,
  }),
});
expect(nullProbe.status === 422, `explicit null player_intents rejected (got ${nullProbe.status})`);
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

fs.writeFileSync(
  ARTIFACT,
  JSON.stringify(
    {
      world_id: wid,
      title: `${TITLE} ${RUN}`,
      absolute_index: advanced.absolute_index,
      actor: 'Wren',
      actor_location_place: 'Market',
      events: eventsBefore,
    },
    null,
    2
  )
);

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
      artifact: ARTIFACT,
    },
    null,
    2
  )
);
