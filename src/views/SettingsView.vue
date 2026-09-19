<!--
  SettingsView — page defaults for NEW stories (existing stories keep their
  own configuration, per the subtitle). AI connections is the fully wired
  section from the mockup; the other sidebar entries render honest
  placeholder panels (their screens haven't been provided yet).

  All field state, dirty tracking and the (fake) connection tests live in
  src/game/settings.ts; this view is markup + composition of the shared
  pieces (PageIntro, SaveBar, StudioSelect, FieldRow, ConnectionCard).

  DEMO scope: Test connection / Generate test image are timer-faked
  transitions in the store — a production client probes the endpoint and,
  for test art, enqueues the image pipeline just like the studios do.
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
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
  applyConnectionTest,
  discardSettings,
  generateTestImage,
  IMAGE_PROVIDERS,
  isSettingsDirty,
  providerModels,
  saveSettings,
  setProvider,
  settings,
  STORY_PROVIDERS,
  type ConnStatus
} from '../game/settings'

/* sections ------------------------------------------------------------- */
const sections = [
  { key: 'ai-connections', label: 'AI connections', icon: IconBranch },
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
  appearance:
    'Text size, contrast, reduced motion and voice-over behaviour will live here. Screen pending.',
  storage: 'Save slots, autosave frequency and export/import for story archives. Screen pending.',
  advanced:
    'Prompt overrides, telemetry and offline models. Most players never visit. Screen pending.'
}

/* dirty / save ---------------------------------------------------------- */
/** Placeholder copy for every section except the designed one. */
const sectionBlurb = computed(() =>
  active.value === 'ai-connections' ? '' : (SECTION_BLURB[active.value] ?? '')
)

const dirty = computed(() => isSettingsDirty())
const savedFlash = ref(false)
let flashTimer: ReturnType<typeof setTimeout> | undefined
function save(): void {
  saveSettings()
  savedFlash.value = true
  clearTimeout(flashTimer)
  flashTimer = setTimeout(() => (savedFlash.value = false), 1400)
}
onBeforeUnmount(() => clearTimeout(flashTimer))

/* connection tests ------------------------------------------------------- */
function connStatus(which: 'story' | 'image'): ConnStatus {
  return settings[which].status
}
let testTimer: ReturnType<typeof setTimeout> | undefined
function testConnection(which: 'story' | 'image'): void {
  if (settings[which].status === 'testing') return
  settings[which].status = 'testing'
  clearTimeout(testTimer)
  // DEMO: fake round-trip; production HEADs the endpoint and reads its
  // capability response.
  testTimer = setTimeout(() => applyConnectionTest(which), 700)
}
onBeforeUnmount(() => clearTimeout(testTimer))

const imageReady = computed(
  () => !!settings.image.provider && settings.image.status === 'reachable'
)
const CAPABILITY_LABEL: Record<string, string> = {
  unknown: 'Unknown',
  supported: 'Supported',
  unsupported: 'Not supported'
}
</script>

<template>
  <main class="settings">
    <header class="settings__head">
      <PageIntro
        title="Settings"
        sub="Defaults for new stories. Existing stories keep their configuration." />
      <span class="settings__rule" aria-hidden="true"></span>
    </header>

    <div class="settings__body">
      <SettingsNav v-model="active" :sections="sections" />

      <div class="settings__main">
        <!-- AI connections (the fully designed screen) -------------------- -->
        <template v-if="active === 'ai-connections'">
          <div
            id="settings-panel-ai-connections"
            role="tabpanel"
            aria-labelledby="settings-tab-ai-connections">
            <h2 class="settings__section">AI connections</h2>
            <p class="settings__section-sub">
              Connect the models that write and illustrate your stories.
            </p>

            <ConnectionCard
              class="settings__card"
              :icon="IconDoc"
              title="Story generation"
              :status="connStatus('story')"
              caption="Used to generate story text, choices, and narrative elements. A successful
                connection only confirms the endpoint is accessible, not that generation works.">
              <FieldRow label="Provider">
                <StudioSelect
                  :model-value="settings.story.provider"
                  :options="STORY_PROVIDERS"
                  @update:model-value="setProvider('story', $event)" />
              </FieldRow>
              <FieldRow label="Model">
                <StudioSelect
                  v-model="settings.story.model"
                  :options="providerModels('story')"
                  placeholder="Select model"
                  :disabled="!settings.story.provider" />
              </FieldRow>
              <FieldRow label="Endpoint" :span="3">
                <input v-model="settings.story.endpoint" class="ev-input" placeholder="http://…" />
              </FieldRow>
              <FieldRow label="Credential reference" :span="2">
                <span class="cred">
                  <span class="cred__lock"><IconLock :size="15" /></span>
                  <input v-model="settings.story.cred" class="cred__input" spellcheck="false" />
                </span>
                <template #after>
                  <div class="testcol">
                    <button
                      type="button"
                      class="testbtn"
                      :disabled="connStatus('story') === 'testing'"
                      @click="testConnection('story')">
                      {{ connStatus('story') === 'testing' ? 'Testing…' : 'Test connection' }}
                    </button>
                    <p v-if="settings.story.lastChecked" class="testcol__note testcol__note--ok">
                      <IconCheck :size="10" /> Last checked {{ settings.story.lastChecked }}
                    </p>
                    <p class="testcol__note">Tests use the values currently entered.</p>
                  </div>
                </template>
              </FieldRow>
            </ConnectionCard>

            <ConnectionCard
              class="settings__card"
              :icon="IconImage"
              title="Image generation"
              :status="connStatus('image')"
              caption="Used to generate scene illustrations and other images for your stories.">
              <FieldRow label="Provider">
                <StudioSelect
                  :model-value="settings.image.provider"
                  :options="IMAGE_PROVIDERS"
                  placeholder="Select provider"
                  @update:model-value="setProvider('image', $event)" />
              </FieldRow>
              <FieldRow label="Model">
                <StudioSelect
                  v-model="settings.image.model"
                  :options="providerModels('image')"
                  placeholder="Select model"
                  :disabled="!settings.image.provider" />
              </FieldRow>
              <FieldRow label="Endpoint" :span="3">
                <input
                  v-model="settings.image.endpoint"
                  class="ev-input"
                  placeholder="https://your-image-provider.example" />
              </FieldRow>
              <FieldRow label="Credential reference" :span="2">
                <span class="cred">
                  <span class="cred__lock"><IconLock :size="15" /></span>
                  <input v-model="settings.image.cred" class="cred__input" spellcheck="false" />
                </span>
                <template #after>
                  <div class="testcol">
                    <button
                      type="button"
                      class="testbtn"
                      :disabled="connStatus('image') === 'testing'"
                      @click="testConnection('image')">
                      {{ connStatus('image') === 'testing' ? 'Testing…' : 'Test connection' }}
                    </button>
                    <p class="testcol__note">Tests use the values currently entered.</p>
                  </div>
                </template>
              </FieldRow>

              <!-- capabilities panel ------------------------------------- -->
              <div class="caps">
                <div class="caps__head">
                  <b>Detected capabilities (after connection test)</b>
                  <div class="caps__act">
                    <button
                      type="button"
                      class="testbtn"
                      :disabled="!imageReady"
                      @click="generateTestImage">
                      <IconImage :size="14" /> Generate test image
                    </button>
                    <p class="testcol__note">
                      Select a provider and verify its capabilities first.
                    </p>
                  </div>
                </div>
                <div class="caps__items">
                  <span class="cap">
                    <span
                      class="cap__ring"
                      :class="`cap__ring--${settings.image.envImages}`"></span>
                    Environment images: {{ CAPABILITY_LABEL[settings.image.envImages] }}
                  </span>
                  <span class="cap">
                    <span class="cap__ring" :class="`cap__ring--${settings.image.charRefs}`"></span>
                    Character references: {{ CAPABILITY_LABEL[settings.image.charRefs] }}
                  </span>
                </div>
              </div>
            </ConnectionCard>
          </div>
        </template>

        <!-- other sections: honest placeholders until their screens exist -->
        <section
          v-else
          class="settings__soon ev-card"
          role="tabpanel"
          :id="`settings-panel-${active}`"
          :aria-labelledby="`settings-tab-${active}`">
          <h2 class="settings__section">{{ activeSection.label }}</h2>
          <p class="settings__soon-copy">{{ sectionBlurb }}</p>
          <p class="ev-info"><IconInfo :size="14" /> This panel is still being written.</p>
        </section>
      </div>
    </div>

    <SaveBar
      :dirty="dirty"
      :saved="savedFlash"
      secondary-label="Discard"
      @secondary="discardSettings">
      <template #end>
        <button type="button" class="cta cta--foot" @click="save">Save settings</button>
      </template>
    </SaveBar>
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
  transition: background 0.14s ease;
}
.testbtn:hover:not(:disabled) {
  background: #f1ead6;
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

/* capabilities panel --------------------------------------------------------*/
.caps {
  grid-column: 1 / -1;
  border: 1px solid #e0d2b0;
  border-radius: 12px;
  background: #f8f1dd;
  padding: 14px 18px 16px;
}
.caps__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
}
.caps__head b {
  font-size: 15.5px;
  font-weight: 600;
  color: var(--ink-2);
}
.caps__act {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 5px;
}
.caps__items {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 30px;
  margin-top: 13px;
}
.cap {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-size: 15px;
  color: var(--ink-2);
}
.cap__ring {
  width: 15px;
  height: 15px;
  border-radius: 50%;
  border: 1.6px solid #b49a68;
  flex: none;
}
.cap__ring--supported {
  border-color: #2e7d43;
  background: radial-gradient(circle, #2e7d43 0 42%, transparent 46%);
}
.cap__ring--unsupported {
  border-color: #b3542e;
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
