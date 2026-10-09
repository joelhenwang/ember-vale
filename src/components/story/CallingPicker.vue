<script setup lang="ts">
/**
 * "Ash joined as a human ranger · Change": a companion who has not fought
 * yet may take another people and calling (callings-001). The server keeps
 * their name, level and experience; `changed` hands back the new sheet.
 */
import { ref } from 'vue'
import type { PartyMemberView } from '../../../content/clients/worldsim'
import { changeCalling, type CallOptions } from '../../api/worldsim'
import { flash } from '../../composables/useEffects'
import { HERO_CLASSES, HERO_RACES, joinedAs } from '../../game/party'

const props = defineProps<{
  member: PartyMemberView
  worldId: string
  opts?: CallOptions
}>()
const emit = defineEmits<{ changed: [member: PartyMemberView] }>()

const open = ref(false)
const race = ref(props.member.race ?? 'human')
const cls = ref(props.member.character_class)
const busy = ref(false)
const error = ref<string | null>(null)
const root = ref<HTMLElement | null>(null)

function start() {
  race.value = props.member.race ?? 'human'
  cls.value = props.member.character_class
  error.value = null
  open.value = true
}

async function save() {
  busy.value = true
  error.value = null
  try {
    const changed = await changeCalling(
      props.member.id,
      {
        world_id: props.worldId,
        race: race.value,
        character_class: cls.value,
        expected_version: props.member.version
      },
      props.opts ?? {}
    )
    open.value = false
    flash(root.value)
    emit('changed', changed)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'That could not be changed.'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div ref="root" class="cp">
    <p class="cp__line">
      {{ joinedAs(member.name, member.race, member.character_class) }}
      <template v-if="!open">
        ·
        <button type="button" class="cp__change ev-press" @click="start">Change</button>
      </template>
    </p>
    <Transition name="ev-rise">
      <form v-if="open" class="cp__form" @submit.prevent="save">
        <label class="cp__field">
          <span>People</span>
          <select v-model="race" :disabled="busy">
            <option v-for="r in HERO_RACES" :key="r.key" :value="r.key">{{ r.name }}</option>
          </select>
        </label>
        <label class="cp__field">
          <span>Calling</span>
          <select v-model="cls" :disabled="busy">
            <option v-for="c in HERO_CLASSES" :key="c.key" :value="c.key">{{ c.name }}</option>
          </select>
        </label>
        <p class="cp__hint">Until {{ member.name }}'s first fight.</p>
        <div class="cp__actions">
          <button type="submit" class="cp__go ev-press" :disabled="busy">
            {{ busy ? 'Changing…' : 'Change' }}
          </button>
          <button type="button" class="cp__cancel ev-press" :disabled="busy" @click="open = false">
            Keep
          </button>
        </div>
        <p v-if="error" class="cp__error" role="alert">{{ error }}</p>
      </form>
    </Transition>
  </div>
</template>

<style scoped>
.cp {
  margin-top: 4px;
  border-radius: 7px;
  font-family: var(--font-ui);
}
.cp__line {
  margin: 0;
  font-size: 13px;
  color: var(--ink-3);
}
.cp__change {
  padding: 0;
  border: 0;
  background: none;
  font: inherit;
  font-weight: 600;
  color: var(--ember);
  cursor: pointer;
}
.cp__change:hover,
.cp__change:focus-visible {
  text-decoration: underline;
}
.cp__form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px 8px;
  margin-top: 6px;
}
.cp__field {
  display: grid;
  gap: 2px;
  min-width: 0;
  font-size: 12px;
  color: var(--muted);
}
.cp__field select {
  min-width: 0;
  padding: 4px 6px;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: var(--surface, transparent);
  color: var(--ink);
  font-family: var(--font-ui);
  font-size: 13.5px;
}
.cp__hint {
  grid-column: 1 / -1;
  margin: 0;
  font-size: 12px;
  color: var(--muted);
}
.cp__actions {
  grid-column: 1 / -1;
  display: flex;
  gap: 8px;
}
.cp__go {
  padding: 4px 14px;
  border: 0;
  border-radius: 999px;
  background: var(--ember);
  color: #fff;
  font-family: var(--font-ui);
  font-size: 13px;
  cursor: pointer;
}
.cp__cancel {
  padding: 4px 12px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: transparent;
  color: var(--ink-2);
  font-family: var(--font-ui);
  font-size: 13px;
  cursor: pointer;
}
.cp__go:disabled,
.cp__cancel:disabled {
  opacity: 0.45;
  cursor: default;
}
.cp__error {
  grid-column: 1 / -1;
  margin: 0;
  color: var(--danger, #b3412e);
  font-size: 12.5px;
}
</style>
