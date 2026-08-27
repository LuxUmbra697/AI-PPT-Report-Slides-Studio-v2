import {
  solveWithFrames,
  type FlexContainer,
  type GroupPreset,
  type PlacedBlock,
  type SkinFrame,
} from '@/render/flexLayout'
import { CANVAS_HEIGHT_PT, CANVAS_WIDTH_PT, type Rect } from '@/render/types'

export type SkinKind =
  | 'fill_box'
  | 'outline_box'
  | 'side_line'
  | 'number_badge'
  | 'timeline_axis'
  | 'timeline_dot'

export type SkinDecoration = {
  kind: SkinKind
  rect: Rect
  color_token: string
  text?: string | null
  radius_pt?: number
}

const BOX_RADIUS_PT = 8.0
const SIDE_LINE_WIDTH_PT = 4.0
const BADGE_SIZE_PT = 18.0
const BADGE_PAD_PT = 4.0
const TIMELINE_AXIS_WIDTH_PT = 2.0
const TIMELINE_DOT_SIZE_PT = 10.0
const TIMELINE_LEFT_PT = 8.0

/** 与 backend/app/domain/flex_skin.py 对齐 */
export function iterSkinDecorations(
  tree: FlexContainer,
  _placed?: PlacedBlock[],
): SkinDecoration[] {
  const { frames } = solveWithFrames(tree)
  return decorationsFromFrames(frames)
}

export function decorationsFromFrames(frames: SkinFrame[]): SkinDecoration[] {
  if (!frames.length) return []

  const byContainer = new Map<string, { preset: GroupPreset; frames: SkinFrame[] }>()
  for (const frame of frames) {
    const key = `${frame.container_id}::${frame.preset}`
    const bucket = byContainer.get(key)
    if (bucket) {
      bucket.frames.push(frame)
    } else {
      byContainer.set(key, { preset: frame.preset, frames: [frame] })
    }
  }

  const decorations: SkinDecoration[] = []
  for (const { preset, frames: group } of byContainer.values()) {
    const sorted = [...group].sort((a, b) => a.child_index - b.child_index)
    switch (preset) {
      case 'solid_boxes':
        decorations.push(...solidBoxes(sorted))
        break
      case 'outline_boxes':
        decorations.push(...outlineBoxes(sorted))
        break
      case 'side_line':
        decorations.push(...sideLines(sorted))
        break
      case 'numbered_steps':
        decorations.push(...numberedSteps(sorted))
        break
      case 'timeline':
        decorations.push(...timeline(sorted))
        break
    }
  }
  return decorations
}

function solidBoxes(frames: SkinFrame[]): SkinDecoration[] {
  return frames.map((frame) => ({
    kind: 'fill_box' as const,
    rect: frame.rect,
    color_token: 'surface',
    radius_pt: BOX_RADIUS_PT,
  }))
}

function outlineBoxes(frames: SkinFrame[]): SkinDecoration[] {
  return frames.map((frame) => ({
    kind: 'outline_box' as const,
    rect: frame.rect,
    color_token: 'line',
    radius_pt: BOX_RADIUS_PT,
  }))
}

function sideLines(frames: SkinFrame[]): SkinDecoration[] {
  const w = SIDE_LINE_WIDTH_PT / CANVAS_WIDTH_PT
  return frames.map((frame) => ({
    kind: 'side_line' as const,
    rect: { x: frame.rect.x, y: frame.rect.y, w, h: frame.rect.h },
    color_token: 'accent',
  }))
}

function numberedSteps(frames: SkinFrame[]): SkinDecoration[] {
  const sizeX = BADGE_SIZE_PT / CANVAS_WIDTH_PT
  const sizeY = BADGE_SIZE_PT / CANVAS_HEIGHT_PT
  const padX = BADGE_PAD_PT / CANVAS_WIDTH_PT
  const padY = BADGE_PAD_PT / CANVAS_HEIGHT_PT
  return frames.map((frame) => ({
    kind: 'number_badge' as const,
    rect: {
      x: frame.rect.x + padX,
      y: frame.rect.y + padY,
      w: sizeX,
      h: sizeY,
    },
    color_token: 'accent',
    text: String(frame.child_index + 1),
    radius_pt: BADGE_SIZE_PT / 2,
  }))
}

function timeline(frames: SkinFrame[]): SkinDecoration[] {
  if (!frames.length) return []

  const left = TIMELINE_LEFT_PT / CANVAS_WIDTH_PT
  const axisW = TIMELINE_AXIS_WIDTH_PT / CANVAS_WIDTH_PT
  const dot = TIMELINE_DOT_SIZE_PT
  const dotX = dot / CANVAS_WIDTH_PT
  const dotY = dot / CANVAS_HEIGHT_PT

  const axisCenterX = frames[0]!.rect.x + left
  const y0 = Math.min(...frames.map((f) => f.rect.y))
  const y1 = Math.max(...frames.map((f) => f.rect.y + f.rect.h))

  const decorations: SkinDecoration[] = [
    {
      kind: 'timeline_axis',
      rect: {
        x: Math.max(0, axisCenterX - axisW / 2),
        y: y0,
        w: axisW,
        h: Math.max(y1 - y0, 1e-9),
      },
      color_token: 'accent',
    },
  ]

  for (const frame of frames) {
    const cx = axisCenterX
    const cy = frame.rect.y + frame.rect.h / 2
    decorations.push({
      kind: 'timeline_dot',
      rect: {
        x: Math.max(0, cx - dotX / 2),
        y: Math.max(0, cy - dotY / 2),
        w: dotX,
        h: dotY,
      },
      color_token: 'accent',
      radius_pt: dot / 2,
    })
  }
  return decorations
}
