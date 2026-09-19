<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { catalog, toggleCharacter, wizard } from '../game/catalog'
import { filterCast, type CastCategory } from '../game/filters'
import MountainRidge from '../components/decor/MountainRidge.vue'
import StoryStepper from '../components/newstory/StoryStepper.vue'
import CastCard from '../components/newstory/CastCard.vue'
import CreateCharacterTile from '../components/newstory/CreateCharacterTile.vue'
import SelectedCastPanel from '../components/newstory/SelectedCastPanel.vue'
import WorldMiniPanel from '../components/newstory/WorldMiniPanel.vue'
import SearchField from '../components/ui/SearchField.vue'
import ChipGroup from '../components/ui/ChipGroup.vue'
import SortSelect from '../components/ui/SortSelect.vue'
import MenuButton from '../components/MenuButton.vue'
import IconSparkle from '../components/icons/IconSparkle.vue'
import IconArrowLeft from '../components/icons/IconArrowLeft.vue'
import IconSave from '../components/icons/IconSave.vue'

const router = useRouter()

/** Typed so ChipGroup's generic v-model keeps the wizard category narrow. */
const categoryOptions: { value: CastCategory; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'companions', label: 'Companions' },
  { value: 'travelers', label: 'Travelers' },
  { value: 'scholars', label: 'Scholars' },
  { value: 'locals', label: 'Locals' }
]

const sortOptions = [
  { value: 'name', label: 'Name' },
  { value: 'recent', label: 'Recently updated' }
]

/** Filtering + sorting are pure and tested in game/filters.ts. */
const cast = computed(() => filterCast(catalog.characters, wizard))

const saved = ref(false)
let savedTimer: ReturnType<typeof setTimeout> | undefined
function saveDraft(): void {
  saved.value = true
  clearTimeout(savedTimer)
  savedTimer = setTimeout(() => (saved.value = false), 1400)
}
</script>

<template>
  <main class="nsv">
    <!-- header band: title + progress + ridge decor -->
    <section class="nsv__band ev-card">
      <MountainRidge class="band__ridge" />
      <div class="band__lead">
        <span class="ev-eyebrow">
          <IconSparkle :size="13" />
          Create a new story
        </span>
        <h1 class="band__title">Choose your cast</h1>
        <p class="band__copy">
          Select the characters who will shape this story. You'll choose how to play in the next
          step.
        </p>
      </div>
      <StoryStepper class="band__stepper" :current="wizard.step" @go="wizard.step = $event" />
      <p class="ev-quote band__quote">“Every story is stronger<br />with good company.”</p>
    </section>

    <div class="nsv__grid">
      <!-- cast picker -->
      <section class="nsv__cast ev-card" aria-label="Characters">
        <div class="cast__head">
          <h2 class="cast__title"><IconSparkle :size="15" /> Characters</h2>
          <span class="cast__rule" aria-hidden="true"></span>
        </div>

        <div class="cast__toolbar">
          <SearchField
            v-model="wizard.search"
            placeholder="Search characters…"
            class="cast__search" />
          <ChipGroup v-model="wizard.category" :options="categoryOptions" />
          <span class="cast__spacer"></span>
          <SortSelect v-model="wizard.sort" label="Sort by" :options="sortOptions" />
        </div>

        <div class="cast__grid">
          <CastCard
            v-for="c in cast"
            :key="c.id"
            :character="c"
            :selected="wizard.selected.includes(c.id)"
            @toggle="toggleCharacter(c.id)" />
          <CreateCharacterTile @create="router.push('/new-story/character/new')" />
          <p v-if="!cast.length" class="cast__none">No one by that name wanders here yet.</p>
        </div>
      </section>

      <aside class="nsv__side">
        <SelectedCastPanel />
        <WorldMiniPanel />
      </aside>
    </div>

    <!-- footer: navigation -->
    <footer class="nsv__foot ev-card">
      <MountainRidge class="foot__ridge" />
      <button type="button" class="ghost" @click="router.push('/')">
        <IconArrowLeft :size="15" /> Back
      </button>
      <button type="button" class="ghost" :class="{ 'ghost--saved': saved }" @click="saveDraft">
        <IconSave :size="14" /> {{ saved ? 'Draft saved' : 'Save draft' }}
      </button>
      <p class="ev-quote foot__quote">“First the people,<br />then the path.”</p>
      <MenuButton class="foot__cta" size="lg" @click="router.push('/play-mode')">
        Continue to Play Mode
      </MenuButton>
    </footer>
  </main>
</template>

<style scoped>
.nsv {
  max-width: 1440px;
  margin: 0 auto;
  padding: 14px 16px 40px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* band ---------------------------------------------------------------------- */
.nsv__band {
  position: relative;
  display: grid;
  grid-template-columns: minmax(300px, 1fr) auto minmax(180px, 300px);
  align-items: center;
  gap: 26px;
  padding: 16px 26px 18px;
  overflow: hidden;
}
.band__ridge {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 430px;
  height: 128px;
  opacity: 0.75;
  pointer-events: none;
}
.band__lead {
  position: relative;
  min-width: 0;
}
.band__title {
  margin-top: 4px;
  font-family: var(--font-display);
  font-size: 41px;
  font-weight: 600;
  line-height: 1.02;
  color: #26200f;
}
.band__copy {
  margin-top: 7px;
  font-size: 16px;
  line-height: 1.4;
  color: var(--ink-2);
}
.band__stepper {
  position: relative;
}
.band__quote {
  position: relative;
  text-align: center;
  font-size: 15.5px;
  line-height: 1.45;
}

/* main grid ------------------------------------------------------------------ */
.nsv__grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 14px;
  align-items: stretch;
}
.nsv__cast {
  padding: 17px 20px 20px;
  min-width: 0;
}
.nsv__side {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

.cast__head {
  display: flex;
  align-items: center;
  gap: 14px;
}
.cast__title {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 600;
  color: #26200f;
}
.cast__title svg {
  color: var(--gold);
}
.cast__rule {
  flex: 1;
  height: 1px;
  background: #e6d9bb;
}

.cast__toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
}
.cast__search {
  flex: 1 1 240px;
  max-width: 340px;
}
.cast__spacer {
  flex: 1;
}

.cast__grid {
  margin-top: 16px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(206px, 1fr));
  gap: 16px;
}
.cast__none {
  grid-column: 1 / -1;
  text-align: center;
  color: var(--muted);
  font-style: italic;
  padding: 24px 0;
}

/* footer ---------------------------------------------------------------------- */
.nsv__foot {
  position: relative;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 18px;
  overflow: hidden;
}
.foot__ridge {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 380px;
  height: 96px;
  opacity: 0.6;
  pointer-events: none;
}
.ghost {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 9px;
  height: 46px;
  padding: 0 20px;
  border-radius: 10px;
  border: 1px solid #cdbb93;
  background: linear-gradient(180deg, #fdf8ea, #f9f1de);
  box-shadow:
    inset 0 1px 0 #fffdf5,
    0 1px 1px rgba(120, 96, 56, 0.08);
  font-size: 17px;
  font-weight: 500;
  color: var(--ink);
  transition:
    background 0.14s ease,
    border-color 0.14s ease,
    color 0.14s ease;
}
.ghost:hover {
  background: linear-gradient(180deg, #fbf4e2, #f4ead2);
  border-color: #b9a577;
}
.ghost--saved {
  color: var(--teal-ink);
  border-color: #8fae9f;
}
.foot__quote {
  margin-left: auto;
  position: relative;
  text-align: right;
  font-size: 14.5px;
  line-height: 1.4;
}
.foot__cta {
  position: relative;
  width: 380px;
  flex: none;
}

@media (max-width: 1250px) {
  .nsv__band {
    grid-template-columns: 1fr;
    row-gap: 18px;
  }
  .band__quote {
    display: none;
  }
  .band__stepper {
    overflow-x: auto;
  }
}
@media (max-width: 1100px) {
  .nsv__grid {
    grid-template-columns: 1fr;
  }
  .foot__quote {
    display: none;
  }
}
</style>
