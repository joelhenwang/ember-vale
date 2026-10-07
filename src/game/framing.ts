/**
 * Frames on a picture: which part of it a layout shows. Vue-free.
 *
 * A frame is x, y (top-left) and w, h in fractions of the picture's width
 * and height, the same shape the server keeps (domain/framing.py). Shapes
 * ("2:3", square) are in pixels, so a frame's fractions depend on the
 * picture's own width and height.
 */

export interface Frame {
  x: number
  y: number
  w: number
  h: number
}

export interface Size {
  width: number
  height: number
}

/** The whole picture. */
export const WHOLE: Frame = { x: 0, y: 0, w: 1, h: 1 }

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))

/** Fraction height of a frame with this fraction width and pixel shape. */
function heightFor(w: number, ratio: number, size: Size): number {
  return (w * size.width) / ratio / size.height
}

/** The largest frame of a pixel shape (width / height) inside `within`, centred. */
export function fit(ratio: number, size: Size, within: Frame = WHOLE): Frame {
  let w = within.w
  let h = heightFor(w, ratio, size)
  if (h > within.h) {
    h = within.h
    w = (h * size.height * ratio) / size.width
  }
  return { x: within.x + (within.w - w) / 2, y: within.y + (within.h - h) / 2, w, h }
}

/** A frame moved by (dx, dy), kept inside `within`. */
export function moveFrame(frame: Frame, dx: number, dy: number, within: Frame = WHOLE): Frame {
  return {
    ...frame,
    x: clamp(frame.x + dx, within.x, within.x + within.w - frame.w),
    y: clamp(frame.y + dy, within.y, within.y + within.h - frame.h)
  }
}

export type Corner = 'nw' | 'ne' | 'sw' | 'se'

/**
 * A frame resized from one corner by dx (fractions of the width), its shape
 * kept and the opposite corner held still; never past `within`, never
 * narrower than `minW`.
 */
export function resizeFrame(
  frame: Frame,
  corner: Corner,
  dx: number,
  ratio: number,
  size: Size,
  within: Frame = WHOLE,
  minW = 0.05
): Frame {
  const west = corner === 'nw' || corner === 'sw'
  const north = corner === 'nw' || corner === 'ne'
  const anchorX = west ? frame.x + frame.w : frame.x
  const anchorY = north ? frame.y + frame.h : frame.y
  // Room toward the moving corner, in width fractions.
  const roomX = west ? anchorX - within.x : within.x + within.w - anchorX
  const roomY = north ? anchorY - within.y : within.y + within.h - anchorY
  const maxW = Math.min(roomX, (roomY * size.height * ratio) / size.width)
  const w = clamp(frame.w + (west ? -dx : dx), Math.min(minW, maxW), maxW)
  const h = heightFor(w, ratio, size)
  return { x: west ? anchorX - w : anchorX, y: north ? anchorY - h : anchorY, w, h }
}

/** A frame kept inside `within` (shrunk to fit if it has to be), shape kept. */
export function keepInside(frame: Frame, ratio: number, size: Size, within: Frame): Frame {
  let { w } = frame
  let h = heightFor(w, ratio, size)
  if (w > within.w || h > within.h) {
    const shrunk = fit(ratio, size, within)
    w = shrunk.w
    h = shrunk.h
  }
  return moveFrame({ x: frame.x, y: frame.y, w, h }, 0, 0, within)
}

/** Where a face usually is on a portrait: a square near the top, centred. */
export function defaultFace(portrait: Frame, size: Size): Frame {
  const w = portrait.w * 0.42
  const h = heightFor(w, 1, size)
  return keepInside(
    { x: portrait.x + (portrait.w - w) / 2, y: portrait.y + portrait.h * 0.1, w, h },
    1,
    size,
    portrait
  )
}

/**
 * A square face frame from a box the map reader found (forehead to chin):
 * a little room around it, centred on it, inside the portrait.
 */
export function faceFromBox(box: Frame, portrait: Frame, size: Size): Frame {
  const sidePx = Math.max(box.w * size.width, box.h * size.height) * 1.25
  const w = sidePx / size.width
  const h = sidePx / size.height
  const cx = box.x + box.w / 2
  const cy = box.y + box.h / 2
  return keepInside({ x: cx - w / 2, y: cy - h / 2, w, h }, 1, size, portrait)
}

/**
 * Style for an <img> inside a box that has the frame's shape, so the box
 * shows exactly the framed part (the box needs position: relative and
 * overflow: hidden).
 */
export function framedStyle(frame: Frame): Record<string, string> {
  return {
    position: 'absolute',
    width: `${100 / frame.w}%`,
    height: `${100 / frame.h}%`,
    left: `${(-frame.x / frame.w) * 100}%`,
    top: `${(-frame.y / frame.h) * 100}%`,
    maxWidth: 'none'
  }
}

/**
 * The frame grown around its centre to a box's shape (width / height), as
 * object-fit: cover would: the framed part stays in view and is never
 * stretched; it shifts rather than leave the picture.
 */
export function coverFrame(frame: Frame, size: Size, boxRatio: number): Frame {
  const fw = frame.w * size.width
  const fh = frame.h * size.height
  let w = fw
  let h = fh
  if (fw / fh < boxRatio) w = Math.min(size.width, fh * boxRatio)
  else h = Math.min(size.height, fw / boxRatio)
  // A picture too narrow (or short) to widen: trim the other side instead.
  if (w / h > boxRatio + 1e-9) w = h * boxRatio
  if (w / h < boxRatio - 1e-9) h = w / boxRatio
  const cx = (frame.x + frame.w / 2) * size.width
  const cy = (frame.y + frame.h / 2) * size.height
  const x = clamp(cx - w / 2, 0, size.width - w)
  const y = clamp(cy - h / 2, 0, size.height - h)
  return { x: x / size.width, y: y / size.height, w: w / size.width, h: h / size.height }
}

/** A frame from the server's [x, y, w, h] list (null when absent or malformed). */
export function frameFromList(raw: unknown): Frame | null {
  if (!Array.isArray(raw) || raw.length !== 4) return null
  const [x, y, w, h] = raw.map(Number)
  if (![x, y, w, h].every((v) => Number.isFinite(v)) || !(w! > 0) || !(h! > 0)) return null
  return { x: x!, y: y!, w: w!, h: h! }
}

/** Parse "2:3" into a pixel shape (width / height). */
export function ratioOf(shape: string): number {
  const [a, b] = shape.split(':').map(Number)
  return a && b ? a / b : 1
}
