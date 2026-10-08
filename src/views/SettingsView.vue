<!--
  SettingsView — storyteller connections that new stories can pin.

  AI connections is wired to the backend (/settings/providers): a
  connection names an adapter, an endpoint and the NAME of a server-side
  environment variable holding the key; model and sampling are
  append-only profile revisions, so stories keep the revision they pinned.
  Connection tests probe the SAVED connection's endpoint (reachability
  only; no credential is sent and no text is generated). Image generation
  edits the operator's image preferences (Krea 2 Studio fields) and can
  paint previews; see ImageSettingsPanel. The other sidebar entries remain
  honest placeholders.

  State and requests live in useProviderSettings / useImageSettings;
  validation and request shaping in src/game/providerSettings.ts and
  src/game/imageSettings.ts.
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import SaveBar from '../components/ui/SaveBar.vue'
import PageIntro from '../components/ui/PageIntro.vue'
import StudioSelect from '../components/studio/StudioSelect.vue'
import SettingsNav from '../components/settings/SettingsNav.vue'
import FieldRow from '../components/settings/FieldRow.vue'
import ConnectionCard from '../components/settings/ConnectionCard.vue'
import IconBranch from '../components/icons/IconBranch.vue'
import IconGear from '../components/icons/IconGear.vue'
import IconMonitor from '../components/icons/IconMonitor.vue'
import IconDatabase from '../components/icons/IconDatabase.vue'
import IconWrench from '../components/icons/IconWrench.vue'
import IconDoc from '../components/icons/IconDoc.vue'
import IconImage from '../components/icons/IconImage.vue'
import IconLock from '../components/icons/IconLock.vue'
import IconCheck from '../components/icons/IconCheck.vue'
import IconInfo from '../components/icons/IconInfo.vue'
import {
  ADAPTER_DEFAULTS,
  ADAPTER_LABELS,
  DEFAULT_MODEL,
  asAdapter
} from '../game/providerSettings'
import type { Adapter } from '../game/providerSettings'
import { NEW_CONNECTION, useProviderSettings } from '../composables/useProviderSettings'
import { useImageSettings } from '../composables/useImageSettings'
import ImageSettingsPanel from '../components/settings/ImageSettingsPanel.vue'
import MotionSettings from '../components/settings/MotionSettings.vue'
import { burst, shake, vRipple } from '../composables/useEffects'

/* sections ------------------------------------------------------------- */
const sections = [
  { key: 'ai-connections', label: 'AI connections', icon: IconBranch },
  { key: 'images', label: 'Image generation', icon: IconImage },
  { key: 'generation', label: 'Generation defaults', icon: IconGear },
  { key: 'appearance', label: 'Appearance & accessibility', icon: IconMonitor },
  { key: 'storage', label: 'Storage & saves', icon: IconDatabase },
  { key: 'advanced', label: 'Advanced', icon: IconWrench }
] as const

type SectionKey = (typeof sections)[number]['key']
const active = ref<SectionKey>('ai-connections')
const activeSection = computed(() => sections.find((s) => s.key === active.value)!)
const SECTION_BLURB: Record<string, string> = {
  generation:
    'Narrator temperature, beat pacing and choice counts get sensible house defaults here. This screen hasn’t been drawn yet — the mockup only covers AI connections.',
  storage: 'Save slots, autosave frequency and export/import for story archives. Screen pending.',
  advanced:
    'Prompt overrides, telemetry and offline models. Most players never visit. Screen pending.'
}
/** Placeholder copy for the sections that have no screen yet. */
const sectionBlurb = computed(() => SECTION_BLURB[active.value] ?? '')

/* storyteller connections ------------------------------------------------ */
const s = useProviderSettings()
const img = useImageSettings()
onMounted(() => {
  void s.load()
  void img.load()
})

const connectionOptions = computed(() => [
  ...s.connections.value.map((c) => ({ value: c.id, label: c.name })),
  { value: NEW_CONNECTION, label: 'New connection…' }
])
const adapterOptions = (Object.keys(ADAPTER_LABELS) as Adapter[]).map((value) => ({
  value,
  label: ADAPTER_LABELS[value]
}))
const MODEL_SUGGESTIONS = ['openrouter/auto', 'mistralai/mistral-nemo']

function selectConnection(id: string): void {
  if (id !== s.selected.value) s.select(id)
}
function setAdapter(value: string): void {
  const adapter = asAdapter(value)
  const form = s.form.value
  const previous = form.adapter
  form.adapter = adapter
  // Swap each value only while it is still the previous adapter's default.
  if (form.modelId === DEFAULT_MODEL[previous]) form.modelId = DEFAULT_MODEL[adapter]
  if (adapter === 'fake') return
  if (form.endpoint === ADAPTER_DEFAULTS[previous].endpoint)
    form.endpoint = ADAPTER_DEFAULTS[adapter].endpoint
  if (form.credentialEnv === ADAPTER_DEFAULTS[previous].credentialEnv || !form.credentialEnv)
    form.credentialEnv = ADAPTER_DEFAULTS[adapter].credentialEnv
}

/** Credential note for the saved connection; unsaved edits are unknown. */
const credentialNote = computed(() => {
  const saved = s.connection.value
  if (!s.form.value.credentialEnv.trim()) return { ok: false, text: 'No key reference set.' }
  if (!saved || s.form.value.credentialEnv.trim() !== (saved.credential_env ?? '')) {
    return { ok: false, text: 'Checked on the server after saving.' }
  }
  return saved.has_credential
    ? { ok: true, text: 'Key found in the server environment.' }
    : { ok: false, text: 'Not set in the server environment yet.' }
})

const revisionNote = computed(() => {
  const rev = s.profile.value?.revision
  return rev
    ? `Revision ${rev}. Saving model changes adds revision ${rev + 1}; stories keep the revision they pinned.`
    : 'Saved as revision 1 of this connection.'
})

function testedAt(iso: string | undefined): string {
  if (!iso) return ''
  const when = new Date(iso)
  return Number.isNaN(when.getTime()) ? iso : when.toLocaleTimeString()
}

/* save bar ---------------------------------------------------------------- */
const savedFlash = ref(false)
let flashTimer: ReturnType<typeof setTimeout> | undefined
async function save(event: MouseEvent): Promise<void> {
  const button = event.currentTarget as HTMLElement | null
  const ok = active.value === 'images' ? await img.save() : await s.save()
  if (!ok) shake(button)
  if (ok) {
    burst(button, { count: 12, spread: 60 })
    savedFlash.value = true
    clearTimeout(flashTimer)
    flashTimer = setTimeout(() => (savedFlash.value = false), 1400)
  }
}
onBeforeUnmount(() => clearTimeout(flashTimer))
</script>

<template>
  <main class="settings">
    <header class="settings__head">
      <PageIntro
        title="Settings"
        sub="The storyteller AI, how pictures are painted, and other choices for the whole game." />
      <span class="settings__rule" aria-hidden="true"></span>
    </header>

    <div class="settings__body">
      <SettingsNav v-model="active" :sections="sections" />

      <div class="settings__main">
        <Transition name="ev-swap" mode="out-in">
          <div v-if="active === 'ai-connections'" key="ai-connections">
            <div
              id="settings-panel-ai-connections"
              role="tabpanel"
              aria-labelledby="settings-tab-ai-connections">
              <h2 class="settings__section">AI connections</h2>
              <p class="settings__section-sub">
                Stories without a pinned connection use the server’s environment default.
              </p>

              <p v-if="s.error.value" class="settings__alert" role="alert">{{ s.error.value }}</p>
              <p v-if="s.loading.value" class="ev-info settings__card">
                <IconInfo :size="14" /> Loading connections<span class="ev-dots" aria-hidden="true"
                  ><span>.</span><span>.</span><span>.</span></span
                >
              </p>

              <ConnectionCard
                v-else
                class="settings__card"
                :icon="IconDoc"
                title="Story generation"
                :status="s.status.value"
                caption="Writes narration, dialogue and character decisions. A reachable endpoint only
                confirms the server can be contacted, not that generation works.">
                <FieldRow label="Connection" :span="3">
                  <StudioSelect
                    :model-value="s.selected.value"
                    :options="connectionOptions"
                    aria-label="Connection"
                    @update:model-value="selectConnection" />
                </FieldRow>
                <FieldRow label="Name">
                  <input v-model="s.form.value.name" class="ev-input" aria-label="Name" />
                  <p v-if="s.errors.value.name" class="field-err">{{ s.errors.value.name }}</p>
                </FieldRow>
                <FieldRow label="Adapter">
                  <StudioSelect
                    :model-value="s.form.value.adapter"
                    :options="adapterOptions"
                    aria-label="Adapter"
                    @update:model-value="setAdapter" />
                </FieldRow>
                <FieldRow label="Endpoint" :span="3">
                  <input
                    v-model="s.form.value.endpoint"
                    class="ev-input"
                    aria-label="Endpoint"
                    placeholder="https://openrouter.ai/api/v1" />
                  <p v-if="s.errors.value.endpoint" class="field-err">
                    {{ s.errors.value.endpoint }}
                  </p>
                  <label class="check">
                    <input v-model="s.form.value.allowLocal" type="checkbox" />
                    Allow a local or private-network endpoint
                  </label>
                </FieldRow>
                <FieldRow label="Key variable" :span="2">
                  <span class="cred">
                    <span class="cred__lock"><IconLock :size="15" /></span>
                    <input
                      v-model="s.form.value.credentialEnv"
                      class="cred__input"
                      spellcheck="false"
                      aria-label="Server environment variable holding the key"
                      placeholder="WORLDSIM_PROVIDER__OPENROUTER_API_KEY" />
                  </span>
                  <p v-if="s.errors.value.credentialEnv" class="field-err">
                    {{ s.errors.value.credentialEnv }}
                  </p>
                  <p class="testcol__note" :class="{ 'testcol__note--ok': credentialNote.ok }">
                    <IconCheck v-if="credentialNote.ok" :size="10" />
                    {{ credentialNote.text }} The key itself never leaves the server.
                  </p>
                  <template #after>
                    <div class="testcol">
                      <button
                        v-ripple
                        type="button"
                        class="testbtn"
                        :disabled="!s.canTest.value"
                        @click="s.test()">
                        <span
                          v-if="s.testing.value"
                          class="testbtn__spin ev-progress-spin"
                          aria-hidden="true"></span>
                        {{ s.testing.value ? 'Testing…' : 'Test connection' }}
                      </button>
                      <p v-if="s.dirty.value || !s.connection.value" class="testcol__note">
                        Save first — tests use the saved connection.
                      </p>
                      <template v-else-if="s.lastTest.value">
                        <p
                          :key="s.lastTest.value.tested_at"
                          class="testcol__note testcol__note--fresh"
                          :class="{ 'testcol__note--ok': s.lastTest.value.reachable }">
                          <IconCheck v-if="s.lastTest.value.reachable" :size="10" />
                          {{ s.lastTest.value.detail }} · {{ testedAt(s.lastTest.value.tested_at) }}
                        </p>
                        <p class="testcol__note">
                          Text generation: {{ s.lastTest.value.text_ready }}
                        </p>
                      </template>
                      <p v-else class="testcol__note">Checks the endpoint; sends no key.</p>
                    </div>
                  </template>
                </FieldRow>

                <h4 class="settings__sub">Model</h4>
                <FieldRow label="Model" :span="3">
                  <input
                    v-model="s.form.value.modelId"
                    class="ev-input"
                    list="settings-model-suggestions"
                    aria-label="Model"
                    spellcheck="false" />
                  <datalist id="settings-model-suggestions">
                    <option v-for="m in MODEL_SUGGESTIONS" :key="m" :value="m" />
                  </datalist>
                  <p v-if="s.errors.value.modelId" class="field-err">
                    {{ s.errors.value.modelId }}
                  </p>
                  <p class="testcol__note">{{ revisionNote }}</p>
                </FieldRow>
                <FieldRow label="Temperature">
                  <input
                    v-model="s.form.value.temperature"
                    class="ev-input"
                    inputmode="decimal"
                    aria-label="Temperature"
                    placeholder="Provider default" />
                  <p v-if="s.errors.value.temperature" class="field-err">
                    {{ s.errors.value.temperature }}
                  </p>
                </FieldRow>
                <FieldRow label="Top P">
                  <input
                    v-model="s.form.value.topP"
                    class="ev-input"
                    inputmode="decimal"
                    aria-label="Top P"
                    placeholder="Provider default" />
                  <p v-if="s.errors.value.topP" class="field-err">{{ s.errors.value.topP }}</p>
                </FieldRow>
                <FieldRow label="Top K">
                  <input
                    v-model="s.form.value.topK"
                    class="ev-input"
                    inputmode="numeric"
                    aria-label="Top K"
                    placeholder="Provider default" />
                  <p v-if="s.errors.value.topK" class="field-err">{{ s.errors.value.topK }}</p>
                </FieldRow>
                <FieldRow label="Max tokens">
                  <input
                    v-model="s.form.value.maxTokens"
                    class="ev-input"
                    inputmode="numeric"
                    aria-label="Max tokens" />
                  <p v-if="s.errors.value.maxTokens" class="field-err">
                    {{ s.errors.value.maxTokens }}
                  </p>
                </FieldRow>
              </ConnectionCard>
            </div>
          </div>

          <div
            v-else-if="active === 'images'"
            id="settings-panel-images"
            role="tabpanel"
            aria-labelledby="settings-tab-images">
            <h2 class="settings__section">Image generation</h2>
            <p class="settings__section-sub">
              How portraits and place art are painted. Changes apply to the next picture, no restart
              needed.
            </p>
            <p v-if="img.loading.value" class="ev-info settings__card">
              <IconInfo :size="14" /> Loading image settings<span class="ev-dots" aria-hidden="true"
                ><span>.</span><span>.</span><span>.</span></span
              >
            </p>
            <ImageSettingsPanel v-else :s="img" />
          </div>

          <div
            v-else-if="active === 'appearance'"
            id="settings-panel-appearance"
            role="tabpanel"
            aria-labelledby="settings-tab-appearance">
            <h2 class="settings__section">Motion</h2>
            <p class="settings__section-sub">
              How much the game moves. Saved on this device and applied at once.
            </p>
            <MotionSettings />
          </div>

          <!-- other sections: honest placeholders until their screens exist -->
          <section
            v-else
            :key="active"
            class="settings__soon ev-card"
            role="tabpanel"
            :id="`settings-panel-${active}`"
            :aria-labelledby="`settings-tab-${active}`">
            <h2 class="settings__section">{{ activeSection.label }}</h2>
            <p class="settings__soon-copy">{{ sectionBlurb }}</p>
            <p class="ev-info"><IconInfo :size="14" /> This panel is still being written.</p>
          </section>
        </Transition>
      </div>
    </div>

    <Transition name="ev-sheet" mode="out-in">
      <SaveBar
        v-if="active === 'ai-connections'"
        :dirty="s.dirty.value"
        :saved="savedFlash"
        secondary-label="Discard"
        @secondary="s.discard()">
        <template #end>
          <button
            type="button"
            class="cta cta--foot"
            :disabled="!s.dirty.value || !s.valid.value || s.saving.value"
            @click="save">
            {{ s.saving.value ? 'Saving…' : 'Save connection' }}
          </button>
        </template>
      </SaveBar>
      <SaveBar
        v-else-if="active === 'images'"
        :dirty="img.dirty.value"
        :saved="savedFlash"
        secondary-label="Discard"
        @secondary="img.discard()">
        <template #end>
          <button
            type="button"
            class="cta cta--foot"
            :disabled="!img.dirty.value || !img.valid.value || img.saving.value"
            @click="save">
            {{ img.saving.value ? 'Saving…' : 'Save image settings' }}
          </button>
        </template>
      </SaveBar>
    </Transition>
  </main>
</template>

<style scoped>
.settings {
  max-width: 1440px;
  margin: 0 auto;
  padding: 14px 16px 40px;
}

.settings__head {
  margin-bottom: 16px;
}
.settings__rule {
  display: block;
  height: 1px;
  background: #e4d6b4;
  margin-top: 14px;
}

.settings__body {
  display: grid;
  grid-template-columns: 262px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}
.settings__main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.settings__section {
  font-family: var(--font-display);
  font-size: 29px;
  font-weight: 600;
  color: var(--ink);
}
.settings__section-sub {
  margin-top: 3px;
  font-size: 15px;
  color: var(--muted);
}
.settings__card {
  margin-top: 16px;
}

/* credential field: lock chip inside a bordered control ------------------- */
.cred {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 44px;
  padding: 0 12px;
  background: #f7faf8;
  border: 1px solid #b9cfd1;
  border-radius: 10px;
}
.cred:focus-within {
  border-color: #5f9488;
  box-shadow: 0 0 0 3px rgba(46, 122, 108, 0.14);
}
.cred__lock {
  width: 30px;
  height: 30px;
  flex: none;
  border: 1px solid #cdbb93;
  border-radius: 8px;
  background: #fbf5e6;
  color: var(--ink);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.cred__input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: transparent;
  font: inherit;
  font-size: 15.5px;
  color: var(--ink);
  letter-spacing: 0.02em;
}
.cred__input:focus {
  outline: none;
}

/* test button column ------------------------------------------------------- */
.testcol {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 5px;
}
.testbtn {
  height: 42px;
  padding: 0 20px;
  border-radius: 10px;
  border: 1px solid #2b6e6a;
  background: #fbf6e9;
  color: var(--teal-ink);
  font-size: 15.5px;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 9px;
  transition:
    background 0.14s ease,
    transform 0.2s var(--ease-settle),
    box-shadow 0.2s ease;
}
.testbtn:hover:not(:disabled) {
  background: #f1ead6;
  transform: translateY(-1px);
  box-shadow: 0 6px 12px -8px rgba(16, 46, 46, 0.4);
}
.testbtn:active:not(:disabled) {
  transform: scale(0.96);
  transition-duration: 0.08s;
}
.testbtn__spin {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid rgba(31, 106, 94, 0.25);
  border-top-color: var(--teal-ink);
  animation: testbtn-spin 0.8s linear infinite;
}
@keyframes testbtn-spin {
  to {
    transform: rotate(360deg);
  }
}
/* a fresh result slides in under the button */
.testcol__note--fresh {
  animation: testcol-in 0.45s var(--ease-settle) both;
}
@keyframes testcol-in {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
}
.testbtn:disabled {
  opacity: 0.55;
  cursor: default;
}
.testcol__note {
  font-size: 13px;
  color: var(--muted);
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.testcol__note--ok {
  color: #2e7d43;
}

/* wired form additions ---------------------------------------------------- */
.settings__sub {
  grid-column: 1 / -1;
  margin: 6px 0 -4px;
  padding-top: 14px;
  border-top: 1px solid #e4d6b4;
  font-size: 15px;
  font-weight: 600;
  color: var(--ink-2);
}
.settings__alert {
  margin-top: 14px;
  padding: 10px 14px;
  border: 1px solid #d6a58c;
  border-radius: 10px;
  background: #fbede5;
  color: #8a3b1c;
  font-size: 14.5px;
}
.field-err {
  margin-top: 4px;
  font-size: 13px;
  color: #b3542e;
}
.check {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  font-size: 14px;
  color: var(--ink-2);
}
.cta:disabled {
  opacity: 0.55;
  cursor: default;
}

/* placeholder sections ------------------------------------------------------ */
.settings__soon {
  padding: 22px 24px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.settings__soon-copy {
  font-size: 15px;
  line-height: 1.5;
  color: var(--ink-2);
  max-width: 62ch;
}

@media (max-width: 980px) {
  .settings__body {
    grid-template-columns: 1fr;
  }
}
</style>
