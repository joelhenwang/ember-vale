/**
 * Backend status for honest capability display (C1/C4).
 *
 * Surfaces readiness without gating onboarding: an empty world table
 * (`seed` degraded) is advisory, and the active model profile (notably
 * `active:fake`) is reported separately so development generation is never
 * presented as a live provider.
 */

import { ref } from 'vue'
import {
  allChecksPass,
  fetchReady,
  isBackendReady,
  modelProfileDetail,
  seedStatus,
  type ReadyResponse
} from '../api/client'

export interface BackendStatus {
  reachable: boolean
  ready: boolean
  checksPass: boolean
  seed: string
  modelProfile: string | null
  migrationHead: string | null
  error: string | null
}

export function useBackend() {
  const status = ref<BackendStatus>({
    reachable: false,
    ready: false,
    checksPass: false,
    seed: 'missing',
    modelProfile: null,
    migrationHead: null,
    error: null
  })
  const loading = ref(false)

  async function refresh(): Promise<void> {
    loading.value = true
    try {
      const body: ReadyResponse = await fetchReady()
      status.value = {
        reachable: true,
        ready: isBackendReady(body),
        checksPass: allChecksPass(body),
        seed: seedStatus(body),
        modelProfile: modelProfileDetail(body),
        migrationHead: body.migration_head ?? null,
        error: null
      }
    } catch (err) {
      status.value = {
        reachable: false,
        ready: false,
        checksPass: false,
        seed: 'missing',
        modelProfile: null,
        migrationHead: null,
        error: err instanceof Error ? err.message : 'backend unreachable'
      }
    } finally {
      loading.value = false
    }
  }

  return { status, loading, refresh }
}
