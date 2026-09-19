<script setup lang="ts">
import { useGameImage } from '../game/images'
import type { ImageSlot } from '../game/model'

/**
 * Resolves a slot through the image registry — generated art when the
 * pipeline has delivered it, placeholder otherwise.
 */
const props = defineProps<{ imageSlot: ImageSlot; alt: string }>()
const url = useGameImage(props.imageSlot)
</script>

<template>
  <img :src="url" :alt="alt" loading="lazy" />
</template>
