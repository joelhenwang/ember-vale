<script setup lang="ts">
/**
 * A fight's dice under the scene they were rolled in: who struck whom with
 * what, the d20 against the defence, and what it did. The storyteller only
 * describes the attempt; these are the numbers the engine rolled.
 */
import { computed, onMounted, ref } from 'vue'
import type { CombatRollView } from '../../../content/clients/worldsim'
import { burst, shake } from '../../composables/useEffects'
import { sayRoll } from '../../game/party'

const props = defineProps<{ rolls: CombatRollView[]; fresh?: boolean }>()

const lines = computed(() => props.rolls.map((r) => ({ roll: r, say: sayRoll(r) })))
const open = ref(true)
const root = ref<HTMLElement | null>(null)

// A fight that just landed answers once: sparks for a critical hit, a jolt
// when the party was hurt.
onMounted(() => {
  if (!props.fresh || !root.value) return
  const crit = root.value.querySelector('.roll--crit .roll__die')
  if (crit) burst(crit, { count: 12, spread: 46 })
  if (root.value.querySelector('.roll--hurt')) shake(root.value)
})
</script>

<template>
  <section ref="root" class="rolls ev-rise" aria-label="The dice for this fight">
    <button type="button" class="rolls__head" :aria-expanded="open" @click="open = !open">
      <span class="rolls__icon" aria-hidden="true">⚄</span>
      The dice
      <span class="rolls__count">{{ rolls.length }} roll{{ rolls.length === 1 ? '' : 's' }}</span>
      <span class="rolls__chev" :class="{ 'rolls__chev--open': open }" aria-hidden="true">›</span>
    </button>
    <ol v-if="open" class="rolls__list">
      <li v-for="(l, i) in lines" :key="i" class="roll" :class="`roll--${l.say.tone}`">
        <span
          v-if="l.say.natural != null"
          class="roll__die"
          :class="{
            'roll__die--20': l.say.natural === 20,
            'roll__die--1': l.say.natural === 1
          }"
          :title="`The die showed ${l.say.natural}`"
          >{{ l.say.natural }}</span
        >
        <span v-else class="roll__die roll__die--none" aria-hidden="true">•</span>
        <span class="roll__body">
          <span class="roll__lead"
            >{{ l.say.lead }}<template v-if="l.say.using"> {{ l.say.using }}</template></span
          >
          <span class="roll__facts">
            <span v-if="l.say.check" class="roll__check">{{ l.say.check }}</span>
            <b v-if="l.say.outcome" class="roll__outcome">{{ l.say.outcome }}</b>
            <span v-if="l.say.hp" class="roll__hp">{{ l.say.hp }}</span>
          </span>
        </span>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.rolls {
  margin: 4px 0 10px;
  border: 1px solid var(--line-soft);
  border-left: 3px solid var(--ember);
  border-radius: 10px;
  background: var(--surface-2);
  font-family: var(--font-ui);
}
.rolls__head {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 10px;
  border: 0;
  background: none;
  font: inherit;
  font-weight: 600;
  font-size: 14.5px;
  color: var(--ink-2);
  cursor: pointer;
  text-align: left;
}
.rolls__icon {
  font-size: 18px;
  line-height: 1;
  color: var(--ember);
}
.rolls__count {
  font-weight: 400;
  color: var(--muted);
}
.rolls__chev {
  margin-left: auto;
  transition: transform 0.25s var(--ease-settle, ease-out);
}
.rolls__chev--open {
  transform: rotate(90deg);
}
.rolls__list {
  list-style: none;
  margin: 0;
  padding: 0 10px 8px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.roll {
  display: grid;
  grid-template-columns: 28px 1fr;
  align-items: start;
  gap: 8px;
}
.roll__die {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 7px;
  border: 1px solid var(--line);
  background: var(--panel);
  font-size: 13px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--ink-2);
}
.roll__die--20 {
  color: #fff7ec;
  border-color: var(--ember);
  background: var(--ember);
}
.roll__die--1 {
  color: var(--muted);
  text-decoration: line-through;
}
.roll__die--none {
  border-style: dashed;
  color: var(--faint);
}
.roll__body {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.roll__lead {
  font-size: 14.5px;
  color: var(--ink);
}
.roll__facts {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  font-size: 13px;
  color: var(--ink-3);
  font-variant-numeric: tabular-nums;
}
.roll--hit .roll__outcome,
.roll--crit .roll__outcome {
  color: var(--teal-ink);
}
.roll--crit .roll__outcome {
  color: var(--ember);
}
.roll--hurt .roll__outcome {
  color: #a8402a;
}
.roll--miss .roll__outcome {
  color: var(--muted);
}
.roll--heal .roll__outcome,
.roll--heal .roll__lead {
  color: #3f7a3a;
}
:root[data-motion='reduced'] .rolls__chev {
  transition: none;
}
@media (prefers-reduced-motion: reduce) {
  :root:not([data-motion='full']) .rolls__chev {
    transition: none;
  }
}
</style>
