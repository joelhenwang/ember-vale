<script setup lang="ts">
import HeroCard from '../components/HeroCard.vue'
import BeginTaleCard from '../components/BeginTaleCard.vue'
import LibraryCard from '../components/LibraryCard.vue'
import RecentStories from '../components/RecentStories.vue'
</script>

<template>
  <main class="page">
    <div class="page__grid">
      <HeroCard />
      <aside class="page__side">
        <BeginTaleCard />
        <LibraryCard />
      </aside>
    </div>
    <RecentStories />
  </main>
</template>

<style scoped>
.page {
  max-width: 1440px;
  margin: 0 auto;
  padding: 14px 16px 40px;
}
.page__grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 474px;
  gap: 14px;
  align-items: stretch;
}
.page__side {
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  gap: 16px;
  min-width: 0;
}

@media (max-width: 1180px) {
  .page__grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .page__side {
    grid-template-rows: auto;
    grid-template-columns: 1fr 1fr;
  }
}
@media (max-width: 900px) {
  .page__side {
    grid-template-columns: 1fr;
  }
}
</style>
