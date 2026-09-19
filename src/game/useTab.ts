import { computed, type WritableComputedRef } from 'vue'
import type { RouteLocationNormalizedLoaded, Router } from 'vue-router'

/**
 * Two-way binding between a page's internal tab and `?tab=` so the current
 * view is shareable/back-button friendly without a second routing layer.
 */
export function useRouteQueryTab(
  route: RouteLocationNormalizedLoaded,
  router: Router,
  fallback: string
): WritableComputedRef<string> {
  return computed({
    get: () => {
      const q = route.query.tab
      return typeof q === 'string' && q.length > 0 ? q : fallback
    },
    set: (tab) => {
      const { tab: _drop, ...rest } = route.query
      router.replace({ query: { ...rest, tab } })
    }
  })
}
