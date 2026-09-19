<script setup lang="ts">
import IconCheck from '../icons/IconCheck.vue'

defineProps<{ steps: string[]; current: number }>()
const emit = defineEmits<{ go: [index: number] }>()
</script>

<template>
  <ol class="istep" aria-label="Creation progress">
    <template v-for="(label, i) in steps" :key="label">
      <li
        class="istep__step"
        :class="
          i + 1 < current
            ? 'istep__step--done'
            : i + 1 === current
              ? 'istep__step--active'
              : 'istep__step--todo'
        ">
        <button
          type="button"
          :aria-current="i + 1 === current ? 'step' : undefined"
          @click="emit('go', i + 1)">
          <span class="istep__circle">
            <IconCheck v-if="i + 1 < current" :size="12" />
            <template v-else>{{ i + 1 }}</template>
          </span>
          <span class="istep__label">{{ label }}</span>
        </button>
      </li>
      <li v-if="i < steps.length - 1" class="istep__link" aria-hidden="true"></li>
    </template>
  </ol>
</template>

<style scoped>
.istep {
  list-style: none;
  display: flex;
  align-items: center;
  gap: 0;
}
.istep__step button {
  display: inline-flex;
  align-items: center;
  gap: 11px;
  padding: 4px 4px;
  border-radius: 10px;
  transition: transform 0.12s ease;
}
.istep__step button:hover {
  transform: translateY(-1px);
}
.istep__circle {
  width: 29px;
  height: 29px;
  flex: none;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 15.5px;
  font-weight: 600;
  background: #fbf5e6;
  border: 1px solid #cdbb93;
  color: #55482f;
  box-shadow:
    inset 0 1px 0 #fffdf5,
    0 1px 2px rgba(96, 74, 40, 0.12);
}
.istep__label {
  font-size: 15.5px;
  font-weight: 500;
  color: #55482f;
  white-space: nowrap;
}
.istep__step--done .istep__circle {
  background: #fbf5e6;
  border-color: #9db39b;
  color: var(--teal-ink);
}
.istep__step--active .istep__circle {
  background: linear-gradient(180deg, #21655f, #14514f);
  border-color: #0f4147;
  color: var(--cream-on-teal);
  box-shadow: 0 1px 2px rgba(16, 46, 46, 0.3);
}
.istep__step--active .istep__label {
  color: var(--teal-ink);
  font-weight: 600;
}
.istep__step--todo .istep__label,
.istep__step--todo .istep__circle {
  color: #8d7c5f;
}
.istep__link {
  width: 42px;
  height: 2px;
  margin: 0 10px;
  border-radius: 2px;
  background: #d5c3a0;
  flex: none;
}
</style>
