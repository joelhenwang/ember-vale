import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

/** Typed route metadata: which flow opened a studio page, and the tab title. */
declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    /** Origin that determines the studio breadcrumb + return route. */
    from?: 'library' | 'new-story'
  }
}

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('./views/HomeView.vue'),
    meta: { title: 'Ember Vale' }
  },
  {
    path: '/new-story',
    name: 'new-story',
    // The wizard opens on step 1 (World); Quick Start pre-fills every step
    // through a persisted server draft instead of skipping ahead.
    component: () => import('./views/NewStoryView.vue'),
    meta: { title: 'New Story — Ember Vale' }
  },
  {
    path: '/library',
    name: 'library',
    component: () => import('./views/LibraryView.vue'),
    meta: { title: 'Library — Ember Vale' }
  },
  {
    path: '/library/character/:id',
    name: 'library-character-studio',
    component: () => import('./views/CharacterStudioView.vue'),
    meta: { title: 'Character — Ember Vale', from: 'library' }
  },
  {
    path: '/new-story/character/:id',
    name: 'wizard-character-studio',
    component: () => import('./views/CharacterStudioView.vue'),
    meta: { title: 'Character — Ember Vale', from: 'new-story' }
  },
  {
    path: '/library/world/:id',
    name: 'library-world-studio',
    component: () => import('./views/WorldStudioView.vue'),
    meta: { title: 'World — Ember Vale', from: 'library' }
  },
  {
    path: '/new-story/world/:id',
    name: 'wizard-world-studio',
    component: () => import('./views/WorldStudioView.vue'),
    meta: { title: 'World — Ember Vale', from: 'new-story' }
  },
  {
    path: '/stories',
    name: 'stories',
    component: () => import('./views/StoriesView.vue'),
    meta: { title: 'Stories — Ember Vale' }
  },
  {
    path: '/stories/:storyId/play',
    name: 'story-play',
    component: () => import('./views/PlayView.vue'),
    meta: { title: 'Story — Ember Vale' }
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('./views/SettingsView.vue'),
    meta: { title: 'Settings — Ember Vale' }
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'unwritten',
    component: () => import('./views/StubView.vue'),
    meta: { title: 'Ember Vale' }
  }
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 })
})

router.afterEach((to) => {
  document.title = to.meta.title ?? 'Ember Vale'
})
