<script setup lang="ts">
/**
 * Play as a new hero: a name, a line about who you are, and you wake in
 * Ember Vale with Wren and Ash about. Your portrait is painted from your
 * words once the story begins.
 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { createDraft, createPreset, createStory, listPresets } from '../api/worldsim'
import { checkHero, heroDraft, heroPreset, type PresetRef } from '../game/quickHero'
import { storyLocation } from '../game/storyRoute'

defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()
const router = useRouter()

const name = ref('')
const about = ref('')
const pronouns = ref('')
const busy = ref(false)
const problem = ref<string | null>(null)
/** One creation identity per dialog: a retried click replays, never doubles. */
const key = `hero-${Math.random().toString(36).slice(2, 10)}`

const step = ref<string>('')
const canStart = computed(() => name.value.trim().length > 0 && !busy.value)

async function begin(): Promise<void> {
  const checked = checkHero({ name: name.value, about: about.value, pronouns: pronouns.value })
  if ('problem' in checked) {
    problem.value = checked.problem
    return
  }
  busy.value = true
  problem.value = null
  try {
    step.value = 'Finding the vale…'
    const [worlds, characters] = await Promise.all([listPresets('world'), listPresets('character')])
    const vale = worlds.find((w) => w.name === 'Ember Vale' && !w.archived) ?? worlds[0]
    if (!vale) throw new Error('No world to start in.')
    const ref = (name: string): PresetRef | null => {
      const found = characters.find((c) => c.name === name && !c.archived)
      return found ? { id: found.id, revision: found.current_revision } : null
    }
    step.value = `Writing ${checked.hero.name} into the world…`
    const created = await createPreset(
      'character',
      checked.hero.name,
      heroPreset(checked.hero),
      `${key}-preset`
    )
    const companions = [
      { name: 'Wren', at: 'hearth' },
      { name: 'Ash', at: 'market' }
    ].flatMap((c) => {
      const found = ref(c.name)
      return found ? [{ name: c.name, ref: found, at: c.at }] : []
    })
    const draft = await createDraft(
      heroDraft(checked.hero, {
        world: { id: vale.id, revision: vale.current_revision },
        hero: { id: created.id, revision: created.current_revision },
        companions
      }),
      'review'
    )
    step.value = 'Opening the story…'
    const story = await createStory(draft.id, draft.version, `${key}-story`)
    emit('close')
    await router.push(storyLocation(story.world_id, 'player'))
  } catch (err) {
    problem.value = err instanceof Error ? err.message : 'The story could not begin. Try again.'
  } finally {
    busy.value = false
    step.value = ''
  }
}
</script>

<template>
  <div
    v-if="open"
    class="hero-dlg"
    role="dialog"
    aria-modal="true"
    aria-label="Play as a new hero"
    @click.self="!busy && emit('close')">
    <form class="hero-dlg__card" @submit.prevent="begin">
      <h2>Who are you?</h2>
      <p class="hero-dlg__lead">
        Wake in Ember Vale as someone new. Your portrait is painted from your words.
      </p>
      <label class="ev-field-label" for="hero-name">Name</label>
      <input
        id="hero-name"
        v-model="name"
        class="ev-input"
        maxlength="64"
        placeholder="Mira, Tobin, Old Sal…"
        :disabled="busy"
        autofocus />
      <label class="ev-field-label" for="hero-about">Who you are</label>
      <textarea
        id="hero-about"
        v-model="about"
        class="ev-input hero-dlg__about"
        maxlength="600"
        rows="3"
        placeholder="A tinker with soot on her cheek and a satchel of half-mended clocks, looking for her runaway brother."
        :disabled="busy" />
      <label class="ev-field-label" for="hero-pronouns">Pronouns (optional)</label>
      <input
        id="hero-pronouns"
        v-model="pronouns"
        class="ev-input"
        maxlength="40"
        placeholder="she/her, he/him, they/them…"
        :disabled="busy" />
      <p v-if="problem" class="hero-dlg__problem" role="alert">{{ problem }}</p>
      <p v-else-if="step" class="hero-dlg__step" role="status">{{ step }}</p>
      <div class="hero-dlg__buttons">
        <button type="button" class="hero-dlg__cancel" :disabled="busy" @click="emit('close')">
          Not now
        </button>
        <button type="submit" class="hero-dlg__go" :disabled="!canStart">Begin</button>
      </div>
    </form>
  </div>
</template>

<style scoped>
.hero-dlg {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: grid;
  place-items: center;
  padding: 16px;
  background: rgba(43, 36, 22, 0.45);
}
.hero-dlg__card {
  width: 100%;
  max-width: 520px;
  background: linear-gradient(180deg, var(--surface-2), var(--surface));
  border: 1px solid var(--line);
  border-radius: var(--radius-card);
  box-shadow: var(--card-shadow);
  padding: 22px 26px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.hero-dlg__card h2 {
  font-family: var(--font-display);
  font-size: 30px;
  color: var(--ink);
}
.hero-dlg__lead {
  color: var(--ink-3);
  margin-bottom: 8px;
}
.hero-dlg__about {
  resize: vertical;
}
.hero-dlg__problem {
  color: #9a3b2b;
}
.hero-dlg__step {
  color: var(--teal-ink);
  font-style: italic;
}
.hero-dlg__buttons {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 10px;
}
.hero-dlg__cancel {
  color: var(--ink-3);
}
.hero-dlg__go {
  background: linear-gradient(180deg, var(--teal-hi), var(--teal));
  color: var(--cream-on-teal);
  border-radius: 10px;
  padding: 8px 22px;
  font-size: 17px;
}
.hero-dlg__go:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
