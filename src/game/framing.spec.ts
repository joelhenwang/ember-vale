import { describe, expect, it } from 'vitest'
import {
  coverFrame,
  defaultFace,
  faceFromBox,
  fit,
  frameFromList,
  framedStyle,
  moveFrame,
  ratioOf,
  resizeFrame,
  type Frame
} from './framing'

const tall = { width: 300, height: 400 } // a 3:4 upload
const px = (f: Frame, size = tall) => ({
  x: f.x * size.width,
  y: f.y * size.height,
  w: f.w * size.width,
  h: f.h * size.height
})

describe('frames', () => {
  it('fits the largest 2:3 frame in a 3:4 picture, centred', () => {
    const frame = fit(ratioOf('2:3'), tall)
    const p = px(frame)
    expect(p.h).toBeCloseTo(400)
    expect(p.w / p.h).toBeCloseTo(2 / 3)
    expect(p.x).toBeCloseTo((300 - p.w) / 2)
  })

  it('moves a frame but never out of the picture', () => {
    const frame = { x: 0.1, y: 0.1, w: 0.5, h: 0.5 }
    expect(moveFrame(frame, 0.9, -0.5)).toEqual({ x: 0.5, y: 0, w: 0.5, h: 0.5 })
  })

  it('resizes from a corner, shape kept and the far corner still', () => {
    const square = fit(1, tall, { x: 0, y: 0, w: 0.5, h: 0.5 })
    const bigger = resizeFrame(square, 'se', 0.2, 1, tall)
    expect(bigger.x).toBeCloseTo(square.x)
    expect(bigger.y).toBeCloseTo(square.y)
    expect(px(bigger).w).toBeCloseTo(px(bigger).h)
    expect(bigger.w).toBeGreaterThan(square.w)
    // From the top-left corner the bottom-right stays put.
    const pulled = resizeFrame(square, 'nw', -0.05, 1, tall)
    expect(pulled.x + pulled.w).toBeCloseTo(square.x + square.w)
    expect(pulled.y + pulled.h).toBeCloseTo(square.y + square.h)
    // Never past the picture.
    const huge = resizeFrame(square, 'se', 5, 1, tall)
    expect(huge.x + huge.w).toBeLessThanOrEqual(1 + 1e-9)
    expect(huge.y + huge.h).toBeLessThanOrEqual(1 + 1e-9)
  })

  it('puts a square face near the top of the portrait, inside it', () => {
    const portrait = fit(ratioOf('2:3'), tall)
    const face = defaultFace(portrait, tall)
    expect(px(face).w).toBeCloseTo(px(face).h)
    expect(face.x).toBeGreaterThanOrEqual(portrait.x)
    expect(face.x + face.w).toBeLessThanOrEqual(portrait.x + portrait.w + 1e-9)
    expect(face.y).toBeLessThan(portrait.y + portrait.h / 3)
  })

  it('squares a found face with a little room, inside the portrait', () => {
    const portrait = fit(ratioOf('2:3'), tall)
    const face = faceFromBox({ x: 0.45, y: 0.1, w: 0.1, h: 0.1 }, portrait, tall)
    expect(px(face).w).toBeCloseTo(px(face).h)
    expect(px(face).w).toBeCloseTo(50) // the longer side, 40 px, plus a quarter
    expect(face.x + face.w / 2).toBeCloseTo(0.5)
  })

  it('shows exactly the framed part', () => {
    expect(framedStyle({ x: 0.25, y: 0.1, w: 0.5, h: 0.25 })).toMatchObject({
      width: '200%',
      height: '400%',
      left: '-50%',
      top: '-40%'
    })
    expect(frameFromList([0.1, 0.2, 0.3, 0.4])).toEqual({ x: 0.1, y: 0.2, w: 0.3, h: 0.4 })
    expect(frameFromList([0.1, 0.2, 0])).toBeNull()
    expect(frameFromList(null)).toBeNull()
  })

  it('grows a frame to a wider box around its centre, never past the picture', () => {
    const portrait = fit(2 / 3, tall) // 200 x 400 px, centred
    const square = coverFrame(portrait, tall, 1)
    expect(px(square).w).toBeCloseTo(px(square).h)
    expect(px(square).w).toBeCloseTo(300) // as wide as the picture allows
    const face = { x: 0.05, y: 0.05, w: 0.1, h: 0.075 } // 30 x 30 px near a corner
    const wide = coverFrame(face, tall, 2)
    expect(px(wide).w / px(wide).h).toBeCloseTo(2)
    expect(wide.x).toBeGreaterThanOrEqual(0) // shifted, not cut
  })
})
