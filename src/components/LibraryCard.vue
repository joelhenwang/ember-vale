<script setup lang="ts">
import { computed } from 'vue'
import IconBook from './icons/IconBook.vue'
import IconGlobe from './icons/IconGlobe.vue'
import IconUsers from './icons/IconUsers.vue'
import IconStack from './icons/IconStack.vue'
import IconArrowRight from './icons/IconArrowRight.vue'

const props = defineProps<{ worlds: number; characters: number; packs: number }>()

/** Counts come from persisted presets so the badges never disagree with
 *  what the Library can actually open for a real story. */
const library = computed(() => [
  {
    icon: IconGlobe,
    count: props.worlds,
    name: 'Worlds',
    note: 'Places to explore'
  },
  {
    icon: IconUsers,
    count: props.characters,
    name: 'Characters',
    note: "People you've met"
  },
  {
    icon: IconStack,
    count: props.packs,
    name: 'Style Pack',
    note: 'Ways to tell your story'
  }
])
</script>

<template>
  <section class="library ev-card" aria-label="Your library">
    <div class="library__head">
      <h2 class="library__title">
        <IconBook :size="22" class="library__book" />
        Your Library
      </h2>
      <router-link class="ev-link" to="/library?tab=characters">
        Open Library
        <IconArrowRight :size="13" class="ev-chevron" />
      </router-link>
    </div>

    <ul class="library__stats">
      <li v-for="stat in library" :key="stat.name" class="library__stat">
        <div class="library__row">
          <component :is="stat.icon" :size="30" class="library__icon" />
          <p class="library__count">
            <strong>{{ stat.count }}</strong>
            <span>{{ stat.name }}</span>
          </p>
        </div>
        <p class="ev-quote library__note">{{ stat.note }}</p>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.library {
  padding: 19px 22px 15px;
  display: flex;
  flex-direction: column;
}

.library__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}
.library__title {
  display: inline-flex;
  align-items: center;
  gap: 11px;
  font-family: var(--font-display);
  font-size: 25px;
  font-weight: 600;
  color: #26200f;
}
.library__book {
  color: var(--gold);
}

/* stats --------------------------------------------------------------------- */
.library__stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  list-style: none;
  margin-top: 15px;
  flex: 1;
}
.library__stat {
  padding: 2px 14px 0 16px;
  min-width: 0;
}
.library__stat + .library__stat {
  border-left: 1px solid #e0d0ab;
}
.library__row {
  display: flex;
  align-items: center;
  gap: 11px;
}
.library__icon {
  color: #a5823f;
  flex: none;
}
.library__count {
  font-size: 16.5px;
  font-weight: 500;
  line-height: 1.15;
  color: #33291a;
}
.library__count strong {
  display: block;
  font-size: 21px;
  font-weight: 600;
}
.library__note {
  margin-top: 6px;
  font-size: 14px;
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

@media (max-width: 1330px) {
  .library__stats {
    grid-template-columns: 1fr;
    gap: 12px;
  }
  .library__stat + .library__stat {
    border-left: 0;
  }
}
</style>
