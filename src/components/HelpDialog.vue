<script setup lang="ts">
/** How to play, in a few lines: opened from the top bar's Help. */
import { onMounted, onUnmounted } from 'vue'

defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()

function onKey(event: KeyboardEvent): void {
  if (event.key === 'Escape') emit('close')
}
onMounted(() => document.addEventListener('keydown', onKey))
onUnmounted(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <Transition name="ev-modal">
    <div
      v-if="open"
      class="help"
      role="dialog"
      aria-modal="true"
      aria-label="How to play"
      @click.self="emit('close')">
      <article class="help__card">
        <header class="help__head">
          <h2>How to play</h2>
          <button type="button" class="help__close" @click="emit('close')">Close</button>
        </header>
        <p class="help__lead">
          Ember Vale is a living story. You play one person in it; everyone else lives their own
          lives, and every turn the whole vale moves on.
        </p>
        <dl class="help__list ev-rise">
          <div>
            <dt>Do</dt>
            <dd>
              Type anything your character tries —
              <i>search the stalls, mend the cart, follow the stranger</i>. The world judges whether
              it works. Heading somewhere by name (<i>walk to the market</i>) takes you there.
            </dd>
          </div>
          <div>
            <dt>Say</dt>
            <dd>
              Speak to someone here, word for word. Click a face in the scene to choose who hears
              you.
            </dd>
          </div>
          <div>
            <dt>Chips</dt>
            <dd>
              One-click moves: go somewhere, look around, pick something up, rest — and leads drawn
              from what you have heard.
            </dd>
          </div>
          <div>
            <dt>Rumours</dt>
            <dd>
              <i>Word around the vale</i> lists openings worth chasing. When one is dealt with, it
              is settled and remembered with how it ended.
            </dd>
          </div>
          <div>
            <dt>Renown</dt>
            <dd>
              New places, new faces, deeds that succeed and rumours settled all earn renown — and
              the vale starts to know your name.
            </dd>
          </div>
          <div>
            <dt>Watching</dt>
            <dd>
              Rather watch than play? Start a story as an observer and open the world map: the cast
              acts on its own while you watch, step by step or on autoplay.
            </dd>
          </div>
        </dl>
        <p class="help__foot">
          Press <kbd>Enter</kbd> to act, <kbd>Shift</kbd>+<kbd>Enter</kbd> for a new line.
        </p>
      </article>
    </div>
  </Transition>
</template>

<style scoped>
.help {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: grid;
  place-items: center;
  padding: 16px;
  background: rgba(43, 36, 22, 0.45);
}
.help__card {
  width: 100%;
  max-width: 620px;
  max-height: 86vh;
  overflow: auto;
  background: linear-gradient(180deg, var(--surface-2), var(--surface));
  border: 1px solid var(--line);
  border-radius: var(--radius-card);
  box-shadow: var(--card-shadow);
  padding: 22px 26px;
}
.help__head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.help__head h2 {
  font-family: var(--font-display);
  font-size: 28px;
  color: var(--ink);
}
.help__close {
  color: var(--teal-ink);
  font-size: 15px;
}
.help__lead {
  margin: 8px 0 14px;
  font-size: 17px;
  color: var(--ink-2);
  line-height: 1.5;
}
.help__list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.help__list div {
  display: grid;
  grid-template-columns: 84px 1fr;
  gap: 12px;
}
.help__list dt {
  font-family: var(--font-display);
  font-size: 18px;
  color: var(--gold);
}
.help__list dd {
  font-size: 15.5px;
  line-height: 1.45;
  color: var(--ink-2);
}
.help__foot {
  margin-top: 14px;
  font-size: 14px;
  color: var(--muted);
}
kbd {
  font-family: inherit;
  border: 1px solid var(--line-strong);
  border-radius: 4px;
  padding: 0 5px;
  background: var(--surface-2);
}
@media (max-width: 560px) {
  .help__list div {
    grid-template-columns: 1fr;
    gap: 2px;
  }
}
</style>
