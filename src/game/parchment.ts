/**
 * A blank parchment to draw a world on when there is no map picture:
 * warm paper with soft blotches, darker edges and a thin border, drawn in
 * the browser and uploaded like any other map. Seeded, so the same size
 * always gives the same sheet.
 */

function seeded(seed: number): () => number {
  let s = seed >>> 0
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0
    return s / 2 ** 32
  }
}

/** A PNG data URL of an empty parchment this size. */
export function parchmentDataUrl(width = 1600, height = 1000, seed = 7): string {
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('This browser cannot draw a parchment.')
  const random = seeded(seed)

  ctx.fillStyle = '#ecdcb4'
  ctx.fillRect(0, 0, width, height)

  // Soft stains, light and dark, of many sizes.
  for (let i = 0; i < 140; i += 1) {
    const x = random() * width
    const y = random() * height
    const r = (0.02 + random() * 0.12) * Math.max(width, height)
    const dark = random() < 0.55
    const glow = ctx.createRadialGradient(x, y, 0, x, y, r)
    glow.addColorStop(0, dark ? 'rgba(150, 112, 58, 0.07)' : 'rgba(255, 246, 220, 0.09)')
    glow.addColorStop(1, 'rgba(0, 0, 0, 0)')
    ctx.fillStyle = glow
    ctx.fillRect(x - r, y - r, r * 2, r * 2)
  }

  // Fibres.
  ctx.lineWidth = 1
  for (let i = 0; i < 900; i += 1) {
    const x = random() * width
    const y = random() * height
    const length = 4 + random() * 18
    const angle = random() * Math.PI
    ctx.strokeStyle = `rgba(120, 88, 44, ${0.04 + random() * 0.06})`
    ctx.beginPath()
    ctx.moveTo(x, y)
    ctx.lineTo(x + Math.cos(angle) * length, y + Math.sin(angle) * length)
    ctx.stroke()
  }

  // Darker, burnt edges.
  const edge = ctx.createRadialGradient(
    width / 2,
    height / 2,
    Math.min(width, height) * 0.35,
    width / 2,
    height / 2,
    Math.hypot(width, height) / 2
  )
  edge.addColorStop(0, 'rgba(0, 0, 0, 0)')
  edge.addColorStop(1, 'rgba(110, 72, 28, 0.42)')
  ctx.fillStyle = edge
  ctx.fillRect(0, 0, width, height)

  // A thin double border, as on old maps.
  const inset = Math.round(Math.min(width, height) * 0.03)
  ctx.strokeStyle = 'rgba(92, 64, 30, 0.55)'
  ctx.lineWidth = 3
  ctx.strokeRect(inset, inset, width - inset * 2, height - inset * 2)
  ctx.lineWidth = 1
  ctx.strokeRect(inset + 8, inset + 8, width - inset * 2 - 16, height - inset * 2 - 16)

  return canvas.toDataURL('image/png')
}
