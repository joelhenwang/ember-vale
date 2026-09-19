<script setup lang="ts">
import IconEmblem from '../components/icons/IconEmblem.vue'
import MountainRidge from '../components/decor/MountainRidge.vue'
</script>

<template>
  <main class="stub">
    <section class="stub__card ev-card">
      <MountainRidge class="stub__ridge" />
      <IconEmblem :size="34" class="stub__mark" />
      <h1 class="stub__title">This chapter is still being written.</h1>
      <p class="stub__copy">
        The narrator hasn't reached this page yet. Wander back to the common room while the ink
        dries.
      </p>
      <router-link to="/" class="stub__link">← Return home</router-link>
    </section>
  </main>
</template>

<style scoped>
.stub {
  max-width: 1440px;
  margin: 0 auto;
  padding: 90px 16px 40px;
  display: flex;
  justify-content: center;
}
.stub__card {
  position: relative;
  overflow: hidden;
  max-width: 560px;
  padding: 44px 48px 48px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.stub__ridge {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 120px;
  opacity: 0.7;
  pointer-events: none;
}
.stub__mark {
  color: #3a3122;
}
.stub__title {
  margin-top: 16px;
  font-family: var(--font-display);
  font-size: 30px;
  font-weight: 600;
  color: #26200f;
}
.stub__copy {
  position: relative;
  margin-top: 10px;
  font-size: 16px;
  line-height: 1.5;
  color: var(--ink-3);
}
.stub__link {
  position: relative;
  margin-top: 20px;
  font-size: 16px;
  font-weight: 500;
  color: var(--teal-ink);
}
.stub__link:hover {
  text-decoration: underline;
  text-underline-offset: 4px;
}
</style>
