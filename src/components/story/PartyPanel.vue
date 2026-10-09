<script setup lang="ts">
/**
 * A combat story's party: the hero and companions with their hit points,
 * armour, level and calling, and the foes of the fight that is on.
 * `full` adds what each one fights with (the Character details drawer).
 * A blow that lands shakes the card it hurt; healing makes it glow.
 * Each one shows their experience toward the next level and, for casters,
 * the spell slots still free today; a level gained throws sparks and a
 * "Level up!" badge (combat level, not the journey renown in the status bar).
 */
import { computed, nextTick, ref, watch } from 'vue'
import type { PartyRosterResponse } from '../../../content/clients/worldsim'
import { burst, flash, shake } from '../../composables/useEffects'
import {
  HERO_CLASSES,
  HERO_RACES,
  choiceName,
  foesStanding,
  hpFraction,
  hpTone,
  partyOrder,
  slotLine,
  slotsLeftLine,
  xpProgress
} from '../../game/party'

const props = withDefaults(
  defineProps<{
    party: PartyRosterResponse
    me: string | null
    full?: boolean
    /** Names who reached a new level in the newest fight (their badge shows). */
    levelled?: string[]
    /** "The party" for the Director and God seats, who play no one in it. */
    title?: string
  }>(),
  { title: 'Your party', levelled: undefined }
)

const members = computed(() => partyOrder(props.party.members ?? [], props.me))
const foes = computed(() => props.party.foes ?? [])
const standing = computed(() => foesStanding(foes.value))

const rows = ref<Record<string, HTMLElement | null>>({})
function rowRef(id: string) {
  return (el: unknown) => {
    rows.value[id] = (el as HTMLElement | null) ?? null
  }
}

// A changed hit-point total answers on the card it belongs to.
watch(
  () => [
    ...members.value.map((m) => [m.id, m.hp_current]),
    ...foes.value.map((f) => [f.key, f.hp_current])
  ],
  async (now, before) => {
    if (!before?.length) return
    const was = new Map(before as [string, number | null][])
    await nextTick()
    for (const [id, hp] of now as [string, number | null][]) {
      const old = was.get(id)
      if (old == null || hp == null || old === hp) continue
      if (hp < old) shake(rows.value[id])
      else flash(rows.value[id])
    }
  }
)

// A level gained while watching throws sparks from the card.
watch(
  () => members.value.map((m) => [m.id, m.level] as [string, number]),
  async (now, before) => {
    if (!before?.length) return
    const was = new Map(before)
    await nextTick()
    for (const [id, level] of now) {
      const old = was.get(id)
      if (old != null && level > old) burst(rows.value[id], { count: 18, spread: 60 })
    }
  }
)

function calling(cls: string, race?: string | null): string {
  const c = choiceName(HERO_CLASSES, cls)
  return race ? `${choiceName(HERO_RACES, race)} ${c.toLowerCase()}` : c
}
</script>

<template>
  <section class="party" :class="{ 'party--full': full }" :aria-label="title">
    <h3 class="party__title">
      {{ title }}
      <span v-if="standing" class="party__fight ev-pop-once">In a fight</span>
    </h3>
    <ul class="party__list">
      <li
        v-for="m in members"
        :key="m.id"
        :ref="rowRef(m.id)"
        class="pm"
        :class="[`pm--${hpTone(m.hp_current, m.hp_max)}`, { 'pm--me': m.character_id === me }]">
        <div class="pm__head">
          <b class="pm__name">{{ m.name }}</b>
          <span v-if="levelled?.includes(m.name)" class="pm__up ev-pop-once">Level up!</span>
          <span class="pm__meta"
            >Level {{ m.level }} {{ calling(m.character_class, full ? m.race : null) }}</span
          >
          <span v-if="m.armor_class != null" class="pm__ac" :title="`Armour class ${m.armor_class}`"
            >AC {{ m.armor_class }}</span
          >
        </div>
        <div class="hp" :aria-label="`${m.hp_current ?? '?'} of ${m.hp_max ?? '?'} hit points`">
          <div class="hp__track">
            <i :style="{ transform: `scaleX(${hpFraction(m.hp_current, m.hp_max)})` }" />
          </div>
          <span class="hp__num">{{ m.hp_current ?? '–' }}/{{ m.hp_max ?? '–' }}</span>
        </div>
        <div
          class="xp"
          :title="`Experience toward level ${m.level + 1}`"
          :aria-label="`Experience: ${xpProgress(m).label}`">
          <div class="xp__track">
            <i :style="{ transform: `scaleX(${xpProgress(m).fraction})` }" />
          </div>
          <span class="xp__num">{{ xpProgress(m).label }}</span>
        </div>
        <p v-if="m.spell_slots?.length" class="pm__slots">
          <span>Spell slots today</span> {{ slotsLeftLine(m) }}
        </p>
        <p v-if="(m.hp_current ?? 1) <= 0" class="pm__down">Down</p>
        <p v-if="m.conditions?.length" class="pm__conds">
          <span v-for="c in m.conditions" :key="c" class="pm__cond">{{ c }}</span>
        </p>
        <template v-if="full">
          <p v-if="m.weapons?.length" class="pm__line">
            <span>Fights with</span> {{ m.weapons.join(', ') }}
          </p>
          <p v-if="m.spells?.length" class="pm__line">
            <span>Spells</span> {{ m.spells.join(', ') }}
          </p>
          <p v-if="m.spell_slots?.length" class="pm__line">
            <span>Spell slots a day</span> {{ slotLine(m.spell_slots) }}
          </p>
        </template>
      </li>
    </ul>
    <Transition name="ev-rise">
      <div v-if="foes.length" class="party__foes">
        <h4>Foes</h4>
        <ul class="party__list">
          <li
            v-for="f in foes"
            :key="f.key"
            :ref="rowRef(f.key)"
            class="pm pm--foe"
            :class="`pm--${hpTone(f.hp_current, f.hp_max)}`">
            <div class="pm__head">
              <b class="pm__name">{{ f.name }}</b>
              <span v-if="f.hp_current <= 0" class="pm__meta">Defeated</span>
              <span class="pm__ac" :title="`Armour class ${f.armor_class}`"
                >AC {{ f.armor_class }}</span
              >
            </div>
            <div class="hp" :aria-label="`${f.hp_current} of ${f.hp_max} hit points`">
              <div class="hp__track">
                <i :style="{ transform: `scaleX(${hpFraction(f.hp_current, f.hp_max)})` }" />
              </div>
              <span class="hp__num">{{ f.hp_current }}/{{ f.hp_max }}</span>
            </div>
          </li>
        </ul>
      </div>
    </Transition>
  </section>
</template>

<style scoped>
.party {
  font-family: var(--font-ui);
}
.party__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 6px;
  font-family: var(--font-display);
  font-size: 19px;
  font-weight: 600;
  color: var(--ink);
}
.party__fight {
  padding: 1px 8px;
  border-radius: 99px;
  font-family: var(--font-ui);
  font-size: 12.5px;
  font-weight: 600;
  color: #fff7ec;
  background: var(--ember);
}
.party__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.pm {
  padding: 6px 9px 7px;
  border: 1px solid var(--line-soft);
  border-radius: 9px;
  background: var(--surface-2);
}
.pm--me {
  border-color: var(--gold-soft);
}
.pm__head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}
.pm__name {
  font-weight: 600;
  font-size: 15px;
  color: var(--ink);
}
.pm__meta {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  font-size: 13px;
  color: var(--ink-3);
}
.pm__ac {
  margin-left: auto;
  padding: 0 6px;
  border: 1px solid var(--line);
  border-radius: 6px;
  font-size: 12px;
  color: var(--ink-2);
}
.hp {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}
.hp__track {
  height: 7px;
  border-radius: 99px;
  background: var(--line-soft);
  overflow: hidden;
}
.hp__track i {
  display: block;
  height: 100%;
  border-radius: 99px;
  transform-origin: left center;
  transition: transform 0.6s var(--ease-settle, ease-out);
  background: linear-gradient(90deg, #4f8a4a, #6fae5e);
}
.pm--hurt .hp__track i {
  background: linear-gradient(90deg, #b5803a, #d6a14d);
}
.pm--low .hp__track i,
.pm--down .hp__track i {
  background: linear-gradient(90deg, #a8402a, #d0603a);
}
.pm--foe .hp__track i {
  background: linear-gradient(90deg, #7b2f22, #b0472f);
}
.pm--down {
  opacity: 0.72;
}
.hp__num {
  font-size: 12.5px;
  font-variant-numeric: tabular-nums;
  color: var(--ink-3);
}
.pm__up {
  padding: 0 7px;
  border-radius: 99px;
  font-size: 12px;
  font-weight: 700;
  color: #fff7ec;
  background: linear-gradient(160deg, var(--ember), #c98a2c);
}
.xp {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 8px;
  margin-top: 3px;
}
.xp__track {
  height: 4px;
  border-radius: 99px;
  background: var(--line-soft);
  overflow: hidden;
}
.xp__track i {
  display: block;
  height: 100%;
  border-radius: 99px;
  transform-origin: left center;
  transition: transform 0.6s var(--ease-settle, ease-out);
  background: linear-gradient(90deg, #c98a2c, var(--ember));
}
.xp__num {
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
  color: var(--muted);
}
.pm__slots {
  margin: 3px 0 0;
  font-size: 12.5px;
  color: var(--ink-2);
}
.pm__slots span {
  color: var(--muted);
  margin-right: 4px;
}
.pm__down {
  margin: 3px 0 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--ember);
}
.pm__conds {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin: 4px 0 0;
}
.pm__cond {
  padding: 0 7px;
  border-radius: 99px;
  font-size: 12px;
  color: var(--teal-ink);
  background: color-mix(in srgb, var(--teal) 10%, transparent);
}
.pm__line {
  margin: 4px 0 0;
  font-size: 13.5px;
  color: var(--ink-2);
}
.pm__line span {
  color: var(--muted);
  margin-right: 4px;
}
.party__foes {
  margin-top: 10px;
}
.party__foes h4 {
  margin: 0 0 5px;
  font-family: var(--font-display);
  font-size: 17px;
  font-weight: 600;
  color: var(--ember);
}
:root[data-motion='reduced'] .hp__track i,
:root[data-motion='reduced'] .xp__track i {
  transition: none;
}
@media (prefers-reduced-motion: reduce) {
  :root:not([data-motion='full']) .hp__track i,
  :root:not([data-motion='full']) .xp__track i {
    transition: none;
  }
}
</style>
