<script setup lang="ts">
/**
 * The choices a level-up left to the player (combat-depth-002): an Ability
 * Score Improvement (+2 to one ability or +1 to two) and, for casters, the
 * spells the level brought, which were picked for them and may be swapped.
 * Each choice is sent on its own; `made` hands back the updated hero.
 */
import { computed, ref } from 'vue'
import type {
  LevelChoiceView,
  PartyMemberView,
  SpellOption
} from '../../../content/clients/worldsim'
import { chooseLevelOption, type CallOptions } from '../../api/worldsim'
import { burst } from '../../composables/useEffects'
import { ABILITIES, abilityMod, addAbilityPoint, improvementReady } from '../../game/party'

const props = defineProps<{
  member: PartyMemberView
  worldId: string
  opts?: CallOptions
}>()
const emit = defineEmits<{ made: [member: PartyMemberView] }>()

const choices = computed(() => props.member.choices ?? [])
const scores = computed(() => props.member.abilities ?? {})
const picks = ref<Record<string, number>>({})
const spells = ref<Record<string, string[]>>({})
const busy = ref<string | null>(null)
const error = ref<string | null>(null)
const root = ref<HTMLElement | null>(null)

function press(key: string) {
  picks.value = addAbilityPoint(picks.value, key, scores.value)
}

function chosenSpells(choice: LevelChoiceView): string[] {
  return spells.value[choice.id] ?? (choice.picked ?? []).map((s) => s.key)
}

function toggleSpell(choice: LevelChoiceView, spell: SpellOption) {
  const now = chosenSpells(choice)
  const want = (choice.picked ?? []).length
  if (now.includes(spell.key)) {
    spells.value = { ...spells.value, [choice.id]: now.filter((k) => k !== spell.key) }
  } else if (now.length < want) {
    spells.value = { ...spells.value, [choice.id]: [...now, spell.key] }
  }
}

/** Every spell the level could teach: the ones picked first, then the rest. */
function spellRows(choice: LevelChoiceView): SpellOption[] {
  const picked = choice.picked ?? []
  const seen = new Set(picked.map((s) => s.key))
  return [...picked, ...(choice.options ?? []).filter((s) => !seen.has(s.key))]
}

async function make(choice: LevelChoiceView) {
  busy.value = choice.id
  error.value = null
  try {
    const made = await chooseLevelOption(
      props.member.id,
      {
        world_id: props.worldId,
        choice_id: choice.id,
        expected_version: props.member.version,
        ...(choice.kind === 'ability'
          ? { abilities: picks.value }
          : { spells: chosenSpells(choice) })
      },
      props.opts ?? {}
    )
    picks.value = {}
    burst(root.value, { count: 14, spread: 50 })
    emit('made', made)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'That choice could not be made.'
  } finally {
    busy.value = null
  }
}
</script>

<template>
  <section v-if="choices.length" ref="root" class="lc" aria-label="Level-up choices">
    <h3 class="lc__title">Level-up choices</h3>
    <div v-for="choice in choices" :key="choice.id" class="lc__choice">
      <template v-if="choice.kind === 'ability'">
        <p class="lc__lead">
          Level {{ choice.level }} makes {{ member.name }} better at something: add
          <b>+2 to one ability</b> or <b>+1 to two</b>.
        </p>
        <div class="lc__abilities">
          <button
            v-for="a in ABILITIES"
            :key="a.key"
            type="button"
            class="ab ev-press"
            :class="{ 'ab--on': picks[a.key] }"
            :aria-pressed="!!picks[a.key]"
            @click="press(a.key)">
            <span class="ab__name">{{ a.name }}</span>
            <b class="ab__score"
              >{{ (scores[a.key] ?? 10) + (picks[a.key] ?? 0) }}
              <small v-if="picks[a.key]">+{{ picks[a.key] }}</small></b
            >
            <span class="ab__mod">{{
              abilityMod((scores[a.key] ?? 10) + (picks[a.key] ?? 0))
            }}</span>
          </button>
        </div>
        <button
          type="button"
          class="lc__go ev-press"
          :disabled="!improvementReady(picks) || busy === choice.id"
          @click="make(choice)">
          {{ busy === choice.id ? 'Choosing…' : 'Choose' }}
        </button>
      </template>
      <template v-else>
        <p class="lc__lead">
          Level {{ choice.level }} taught {{ member.name }}
          {{
            (choice.picked ?? []).length === 1
              ? 'a spell'
              : `${(choice.picked ?? []).length} spells`
          }}.
          {{
            (choice.picked ?? []).length === 1
              ? 'Keep it, or pick another'
              : 'Keep them, or pick others'
          }}.
        </p>
        <ul class="lc__spells">
          <li v-for="s in spellRows(choice)" :key="s.key">
            <label class="sp" :class="{ 'sp--on': chosenSpells(choice).includes(s.key) }">
              <input
                type="checkbox"
                :checked="chosenSpells(choice).includes(s.key)"
                @change="toggleSpell(choice, s)" />
              <span>{{ s.name }}</span>
              <small>{{ s.level === 0 ? 'cantrip' : `level ${s.level}` }}</small>
            </label>
          </li>
        </ul>
        <button
          type="button"
          class="lc__go ev-press"
          :disabled="
            chosenSpells(choice).length !== (choice.picked ?? []).length || busy === choice.id
          "
          @click="make(choice)">
          {{ busy === choice.id ? 'Learning…' : 'Learn these' }}
        </button>
      </template>
    </div>
    <p v-if="error" class="lc__error" role="alert">{{ error }}</p>
  </section>
</template>

<style scoped>
.lc {
  display: grid;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--ember);
  border-radius: 10px;
  background: color-mix(in srgb, var(--ember) 6%, transparent);
}
.lc__title {
  margin: 0;
  font-family: var(--font-ui);
  font-size: 0.95rem;
  color: var(--ink);
}
.lc__choice {
  display: grid;
  gap: 8px;
}
.lc__lead {
  margin: 0;
  font-family: var(--font-body);
  color: var(--ink-2);
  line-height: 1.45;
}
.lc__abilities {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
}
.ab {
  display: grid;
  gap: 2px;
  justify-items: center;
  padding: 6px 4px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: transparent;
  color: var(--ink-2);
  font-family: var(--font-ui);
  cursor: pointer;
}
.ab--on {
  border-color: var(--ember);
  color: var(--ink);
  background: color-mix(in srgb, var(--ember) 12%, transparent);
}
.ab__name {
  font-size: 0.75rem;
}
.ab__score {
  font-size: 1.05rem;
  font-variant-numeric: tabular-nums;
}
.ab__score small {
  color: var(--ember);
  font-size: 0.7rem;
}
.ab__mod {
  font-size: 0.72rem;
  color: var(--ink-3);
}
.lc__spells {
  display: grid;
  gap: 4px;
  max-height: 220px;
  overflow-y: auto;
  margin: 0;
  padding: 0;
  list-style: none;
}
.sp {
  display: flex;
  gap: 8px;
  align-items: baseline;
  font-family: var(--font-ui);
  color: var(--ink-2);
  cursor: pointer;
}
.sp--on {
  color: var(--ink);
}
.sp small {
  margin-left: auto;
  color: var(--ink-3);
}
.lc__go {
  justify-self: start;
  padding: 6px 16px;
  border: 0;
  border-radius: 999px;
  background: var(--ember);
  color: #fff;
  font-family: var(--font-ui);
  cursor: pointer;
}
.lc__go:disabled {
  opacity: 0.45;
  cursor: default;
}
.lc__error {
  margin: 0;
  color: var(--danger, #b3412e);
  font-family: var(--font-ui);
  font-size: 0.85rem;
}
</style>
