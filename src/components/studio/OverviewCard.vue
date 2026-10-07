<!--
  OverviewCard — the first step of a studio: the player's own overview of
  a character or a world, with two helpers. "Improve my overview" asks a
  model for a fuller version and shows it beside theirs; nothing changes
  until they choose it. "Fill the empty fields" asks the host to write the
  fields they left empty from this overview (the host knows its fields).
-->
<script setup lang="ts">
import { ref } from 'vue'
import { enhanceOverview } from '../../api/worldsim'
import IconSparkle from '../icons/IconSparkle.vue'
import IconFeather from '../icons/IconFeather.vue'

const props = defineProps<{
  kind: 'character' | 'world'
  name: string
  placeholder: string
  /** Fields still empty across the whole studio (0 hides the fill button's count). */
  empty: number
  /** The host is filling fields right now. */
  filling: boolean
  /** The host's last fill: what happened, or what went wrong. */
  fillNote?: string | null
}>()
const overview = defineModel<string>({ required: true })
defineEmits<{ fill: [] }>()

const improving = ref(false)
const proposal = ref<string | null>(null)
const note = ref<string | null>(null)
const failed = ref(false)

async function improve(): Promise<void> {
  if (!overview.value.trim() || improving.value) return
  improving.value = true
  note.value = null
  failed.value = false
  try {
    const made = await enhanceOverview(props.kind, overview.value, props.name)
    proposal.value = made.text
    note.value = `Written in ${Number(made.seconds).toFixed(0)} s for $${Number(made.cost_usd).toFixed(4)}.`
  } catch (err) {
    failed.value = true
    note.value = err instanceof Error ? err.message : 'Could not improve it this time.'
  } finally {
    improving.value = false
  }
}

function useProposal(): void {
  if (proposal.value) overview.value = proposal.value
  proposal.value = null
  note.value = 'Using the improved overview. Fill the empty fields from it whenever you like.'
}
</script>

<template>
  <section class="ovw card ev-card">
    <header class="card__head">
      <h2 class="card__title"><IconFeather :size="18" /> Overview</h2>
    </header>
    <textarea
      v-model="overview"
      class="ev-input ovw__text"
      rows="7"
      maxlength="6000"
      :placeholder="placeholder"
      :aria-label="`${kind === 'world' ? 'World' : 'Character'} overview`" />

    <Transition name="ovw-pop">
      <div v-if="proposal" class="ovw__proposal" aria-live="polite">
        <p class="ovw__proposal-head"><IconSparkle :size="13" /> An improved overview</p>
        <p class="ovw__proposal-text">{{ proposal }}</p>
        <div class="ovw__proposal-actions">
          <button type="button" class="cta cta--sm" @click="useProposal">Use this one</button>
          <button type="button" class="ghost ghost--sm" @click="proposal = null">Keep mine</button>
          <button type="button" class="ghost ghost--sm" :disabled="improving" @click="improve">
            {{ improving ? 'Writing…' : 'Try again' }}
          </button>
        </div>
      </div>
    </Transition>

    <div class="ovw__actions">
      <button
        type="button"
        class="ovw__btn"
        :disabled="!overview.trim() || improving"
        :title="overview.trim() ? '' : 'Write a few words first'"
        @click="improve">
        <IconSparkle :size="15" />
        {{ improving ? 'Improving…' : 'Improve my overview' }}
      </button>
      <button
        type="button"
        class="ovw__btn ovw__btn--fill"
        :disabled="filling || empty === 0"
        @click="$emit('fill')">
        <IconSparkle :size="15" />
        {{
          filling
            ? 'Filling the empty fields…'
            : empty === 0
              ? 'Every field is filled'
              : `Fill the ${empty} empty field${empty === 1 ? '' : 's'}`
        }}
      </button>
    </div>
    <p v-if="note" class="ovw__note" :class="{ 'ovw__note--bad': failed }" role="status">
      {{ note }}
    </p>
    <p v-if="fillNote" class="ovw__note" role="status">{{ fillNote }}</p>
    <p class="ovw__hint">
      The helpers never overwrite what you wrote: filling only writes into empty fields, and an
      improved overview waits for you to choose it.
    </p>
  </section>
</template>

<style scoped>
.ovw__text {
  min-height: 170px;
  font-size: 17px;
  line-height: 1.55;
}
.ovw__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
}
.ovw__btn {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  height: 42px;
  padding: 0 18px;
  border-radius: 10px;
  border: 1px solid #9dbfb4;
  background: linear-gradient(180deg, #f4faf3, #e9f3ea);
  color: #1f5a52;
  font-size: 16px;
  font-weight: 500;
  box-shadow:
    inset 0 1px 0 #ffffffb0,
    0 4px 10px -6px rgba(31, 90, 82, 0.4);
  transition:
    transform 0.18s var(--ease-out),
    box-shadow 0.18s var(--ease-out),
    border-color 0.15s ease;
}
.ovw__btn svg {
  color: var(--ember);
  transition: transform 0.5s var(--ease-spring);
}
.ovw__btn:hover:not(:disabled) {
  transform: translateY(-1px);
  border-color: #5f9488;
  box-shadow:
    inset 0 1px 0 #ffffffb0,
    0 8px 16px -8px rgba(31, 90, 82, 0.5),
    0 0 0 3px var(--ember-glow);
}
.ovw__btn:hover:not(:disabled) svg {
  transform: rotate(90deg) scale(1.15);
}
.ovw__btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.ovw__btn--fill {
  border-color: #d9b48a;
  background: linear-gradient(180deg, #fdf3e6, #f8e6cf);
  color: #7a3f17;
}
.ovw__proposal {
  margin-top: 14px;
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid #e0c9a0;
  border-left: 4px solid var(--ember);
  background: linear-gradient(180deg, #fffaf0, #fbf1de);
}
.ovw__proposal-head {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-family: var(--font-ui);
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ember);
}
.ovw__proposal-text {
  margin-top: 8px;
  font-size: 16.5px;
  line-height: 1.6;
  white-space: pre-line;
  color: var(--ink);
}
.ovw__proposal-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}
.ovw__note {
  margin-top: 10px;
  font-family: var(--font-ui);
  font-size: 15px;
  color: var(--ink-3);
}
.ovw__note--bad {
  color: #b3542e;
}
.ovw__hint {
  margin-top: 8px;
  font-size: 14.5px;
  color: var(--muted);
}
.ovw-pop-enter-active {
  transition:
    opacity 0.3s ease,
    transform 0.35s var(--ease-spring);
}
.ovw-pop-enter-from {
  opacity: 0;
  transform: translateY(-6px) scale(0.98);
}
</style>
