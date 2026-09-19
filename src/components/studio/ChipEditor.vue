<script setup lang="ts">
import { nextTick, ref } from 'vue'
import IconX from '../icons/IconX.vue'
import IconPlus from '../icons/IconPlus.vue'

const model = defineModel<string[]>({ default: () => [] })

const adding = ref(false)
const draft = ref('')
const inputEl = ref<HTMLInputElement | null>(null)

async function startAdd(): Promise<void> {
  adding.value = true
  draft.value = ''
  await nextTick()
  inputEl.value?.focus()
}
function commit(): void {
  const v = draft.value.trim()
  if (v && !model.value.includes(v)) model.value = [...model.value, v]
  adding.value = false
}
function remove(tag: string): void {
  model.value = model.value.filter((t) => t !== tag)
}
</script>

<template>
  <div class="ce">
    <span v-for="tag in model" :key="tag" class="ce__chip">
      {{ tag }}
      <button type="button" :aria-label="`Remove ${tag}`" @click="remove(tag)">
        <IconX :size="11" />
      </button>
    </span>
    <input
      v-if="adding"
      ref="inputEl"
      v-model="draft"
      class="ce__add ce__add--editing"
      placeholder="New trait…"
      @keydown.enter.prevent="commit"
      @keydown.esc="adding = false"
      @blur="commit" />
    <button v-else type="button" class="ce__add" @click="startAdd">
      <IconPlus :size="12" /> Add
    </button>
  </div>
</template>

<style scoped>
.ce {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.ce__chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 31px;
  padding: 0 8px 0 13px;
  border-radius: 999px;
  background: #e4eef0;
  border: 1px solid #c4d6d9;
  font-size: 14px;
  font-weight: 500;
  color: #3d4b46;
}
.ce__chip button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  color: #7d8f8a;
  transition:
    background-color 0.12s ease,
    color 0.12s ease;
}
.ce__chip button:hover {
  background: #cfddde;
  color: #6e3b2c;
}
.ce__add {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 31px;
  padding: 0 14px;
  border-radius: 999px;
  border: 1px solid #cdbb93;
  background: #fbf5e6;
  font-size: 14px;
  font-weight: 500;
  color: var(--ink-2);
  transition:
    border-color 0.14s ease,
    background-color 0.14s ease;
}
.ce__add:hover {
  border-color: #b39c6d;
  background: #f6eeda;
}
.ce__add--editing {
  width: 130px;
  padding: 0 12px;
  border-color: #5f9488;
  background: #f7faf8;
  outline: none;
}
</style>
