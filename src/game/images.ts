import { computed, reactive, type ComputedRef } from 'vue'
import type { ImageSlot } from './model'

/**
 * Image registry for the whole app.
 *
 * The UI never imports image files directly — it asks for a `slot` and gets
 * a reactive URL back. Today the answers are placeholders (a mix of the
 * hand-supplied concept art, crops of the design mockups, and sample renders
 * from an image model). In production the flow is:
 *
 *   narrator emits scene state
 *        → prompt composer builds an art-direction prompt (style pack + lore)
 *        → image model renders → result cached by prompt hash / story+day
 *        → `setGeneratedImage(slot, url)` swaps it in; every card re-renders.
 *
 * Until a slot has a generated image (or if generation fails / is loading),
 * the placeholder is returned, so the UI always looks complete.
 */

const PLACEHOLDER_URLS: Record<ImageSlot, string> = {
  'hero.currentStory': '/images/hero-ember-vale.webp',
  'story.ashes': '/images/story-ashes.webp',
  'story.lantern': '/images/story-lantern.webp',
  'player.avatar': '/images/avatar-lyria.webp',
  'scene.hearth': '/images/hearth-background.webp',
  'scene.market': '/images/market-background.webp',
  'character.wren': '/images/character-wren.webp',
  'character.ash': '/images/character-ash.webp',
  'character.lyria': '/images/character-lyria.webp',
  'character.miri': '/images/character-miri.webp',
  'character.thomas': '/images/character-thomas.webp',
  'character.nessa': '/images/character-nessa.webp',
  'world.emberVale': '/images/world-ember-vale.webp',
  'world.silverleaf': '/images/world-silverleaf.webp',
  'world.map': '/images/hero-ember-vale.webp',
  'character.wren.fullbody': '/images/character-wren-fullbody.webp',
  'library.banner': '/images/library-banner.webp'
}

/** Images delivered by the (future) generation pipeline, keyed by slot. */
const generated = reactive<Partial<Record<ImageSlot, string>>>({})

/** Feed a freshly generated image into the UI (swap-in from the art pipeline). */
export function setGeneratedImage(slot: ImageSlot, url: string): void {
  generated[slot] = url
}

/** Reactive art for a slot — generated image when available, else placeholder. */
export function useGameImage(slot: ImageSlot): ComputedRef<string> {
  return computed(() => resolveImage(slot))
}

/** One-shot resolution; also reactive when read inside a computed(). */
export function resolveImage(slot: ImageSlot): string {
  return generated[slot] ?? PLACEHOLDER_URLS[slot]
}
