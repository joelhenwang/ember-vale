// Make a story to photograph: the built-in vale, Wren as the player, five
// turns with the fake model (no spend). Prints the story id.
//   node setup-story.mjs [api base]   (reads WORLDSIM_SECURITY__API_KEY)
const base = process.argv[2] ?? 'http://localhost:8104'
const headers = {
  'content-type': 'application/json',
  authorization: `Bearer ${process.env.WORLDSIM_SECURITY__API_KEY}`
}
async function call(method, path, body, extra = {}) {
  const res = await fetch(`${base}/api/v1${path}`, {
    method,
    headers: { ...headers, ...extra },
    body: body ? JSON.stringify(body) : undefined
  })
  const text = await res.text()
  if (!res.ok) throw new Error(`${method} ${path} -> ${res.status} ${text.slice(0, 300)}`)
  return text ? JSON.parse(text) : null
}
const draft = await call('POST', '/story-drafts', {
  payload: {
    world: { preset_id: '20000000-0000-4000-8000-000000000001', preset_revision: 2 },
    cast: [
      {
        instance_key: 'cast-wren',
        preset_id: '20000000-0000-4000-8000-000000000101',
        preset_revision: 1,
        name: 'Wren',
        location_key: 'hearth'
      },
      {
        instance_key: 'cast-ash',
        preset_id: '20000000-0000-4000-8000-000000000102',
        preset_revision: 1,
        name: 'Ash',
        location_key: 'market'
      }
    ],
    mode: { role: 'player', controlled_cast_key: 'cast-wren' },
    story: { title: process.argv[3] ?? 'The Ledger' }
  },
  current_step: 'review'
})
const story = await call(
  'POST',
  '/stories',
  { draft_id: draft.id, expected_draft_version: 1 },
  { 'Idempotency-Key': `shots-${Date.now()}` }
)
const world = story.world_id
const wren = story.character_id
for (let index = 1; index <= 5; index++) {
  const intent =
    index % 2
      ? { family: 'observe', focus: 'the square' }
      : { family: 'wait' }
  await call('POST', '/stage1/advance', {
    world_id: world,
    absolute_index: index,
    player_intents: {
      [wren]: {
        ...intent,
        character_id: wren,
        snapshot_id: '00000000-0000-4000-8000-000000000000'
      }
    }
  })
}
console.log(world)
