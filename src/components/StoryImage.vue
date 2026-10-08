<script setup lang="ts">
import { ref, watch } from 'vue'
import { useGameImage } from '../game/images'
import type { ImageSlot } from '../game/model'

/**
 * Resolves a slot through the image registry — generated art when the
 * pipeline has delivered it, placeholder otherwise. The picture fades in
 * once it has loaded (or failed), never popping in half-drawn.
 */
const props = defineProps<{ imageSlot: ImageSlot; alt: string }>()
const url = useGameImage(props.imageSlot)
const loaded = ref(false)
watch(url, () => (loaded.value = false))
</script>

<template>
  <img
    :src="url"
    :alt="alt"
    loading="lazy"
    decoding="async"
    class="ev-img-fade"
    :class="{ 'is-loaded': loaded }"
    @load="loaded = true"
    @error="loaded = true" />
</template>
