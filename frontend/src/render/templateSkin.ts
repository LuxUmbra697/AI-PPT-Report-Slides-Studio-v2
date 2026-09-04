import type { SkinDecoration } from '@/render/flexSkin'
import type { Rect, Theme } from '@/render/types'

/** 与 backend/app/domain/template_skin.py 对齐：主题不只换色，也改变页面骨架。 */
export function iterTemplateDecorations(
  theme: Theme,
  layoutId: string,
  occupied: Rect[],
): SkinDecoration[] {
  const visual = theme.visual ?? {
    family: 'classic',
    cover_variant: 'editorial',
    content_variant: 'clean',
    transition: 'fade',
  }
  if (layoutId === 'cover') return coverDecorations(visual.cover_variant)

  const body = bodyRects(occupied)
  switch (visual.content_variant) {
    case 'cards':
      return cards(body)
    case 'notebook':
      return notebook(body)
    case 'dashboard':
      return dashboard(body)
    case 'magazine':
      return magazine(body)
    case 'panel':
      return panel(body)
    default:
      return clean(occupied)
  }
}

function bodyRects(rects: Rect[]): Rect[] {
  const body = rects.filter((rect) => rect.y >= 0.2 || rect.h >= 0.24)
  return [...(body.length ? body : rects)].sort((a, b) => a.y - b.y || a.x - b.x)
}

function expand(rect: Rect, dx = 0.012, dy = 0.018): Rect {
  const x = Math.max(0.025, rect.x - dx)
  const y = Math.max(0.03, rect.y - dy)
  const right = Math.min(0.975, rect.x + rect.w + dx)
  const bottom = Math.min(0.97, rect.y + rect.h + dy)
  return { x, y, w: Math.max(0.001, right - x), h: Math.max(0.001, bottom - y) }
}

function coverDecorations(variant: NonNullable<Theme['visual']>['cover_variant']): SkinDecoration[] {
  switch (variant) {
    case 'split':
      return [
        { kind: 'fill_box', rect: { x: 0.61, y: 0, w: 0.39, h: 1 }, color_token: 'surface' },
        {
          kind: 'side_line',
          rect: { x: 0.595, y: 0.08, w: 0.004, h: 0.84 },
          color_token: 'accent',
        },
      ]
    case 'framed':
      return [
        {
          kind: 'outline_box',
          rect: { x: 0.045, y: 0.08, w: 0.91, h: 0.84 },
          color_token: 'line_strong',
          radius_pt: 10,
        },
        {
          kind: 'outline_box',
          rect: { x: 0.062, y: 0.11, w: 0.876, h: 0.78 },
          color_token: 'line',
          radius_pt: 7,
        },
      ]
    case 'poster':
      return [
        {
          kind: 'side_line',
          rect: { x: 0.075, y: 0.1, w: 0.008, h: 0.8 },
          color_token: 'accent',
        },
        {
          kind: 'side_line',
          rect: { x: 0.1, y: 0.875, w: 0.35, h: 0.006 },
          color_token: 'line_strong',
        },
      ]
    case 'spotlight':
      return [
        {
          kind: 'timeline_dot',
          rect: { x: 0.66, y: 0.16, w: 0.24, h: 0.42 },
          color_token: 'accent_soft',
        },
        {
          kind: 'timeline_dot',
          rect: { x: 0.745, y: 0.35, w: 0.12, h: 0.21 },
          color_token: 'surface',
        },
      ]
    case 'ribbon':
      return [
        {
          kind: 'fill_box',
          rect: { x: 0, y: 0.79, w: 0.72, h: 0.12 },
          color_token: 'accent_soft',
          radius_pt: 8,
        },
        {
          kind: 'side_line',
          rect: { x: 0, y: 0.91, w: 0.48, h: 0.012 },
          color_token: 'accent',
        },
      ]
    default:
      return [
        {
          kind: 'side_line',
          rect: { x: 0.07, y: 0.2, w: 0.006, h: 0.5 },
          color_token: 'accent',
        },
      ]
  }
}

function cards(rects: Rect[]): SkinDecoration[] {
  return rects.flatMap((rect) => {
    const frame = expand(rect)
    return [
      { kind: 'fill_box', rect: frame, color_token: 'surface', radius_pt: 14 },
      { kind: 'outline_box', rect: frame, color_token: 'line', radius_pt: 14 },
    ]
  })
}

function dashboard(rects: Rect[]): SkinDecoration[] {
  return rects.flatMap((rect, index) => {
    const frame = expand(rect, 0.01, 0.014)
    return [
      {
        kind: 'outline_box' as const,
        rect: frame,
        color_token: 'line_strong',
        radius_pt: 5,
      },
      {
        kind: 'fill_box' as const,
        rect: {
          x: frame.x + 0.012,
          y: frame.y,
          w: Math.min(0.075, frame.w * 0.28),
          h: Math.min(0.012, frame.h),
        },
        color_token: index % 2 === 0 ? 'accent' : 'accent_soft',
        radius_pt: 3,
      },
    ]
  })
}

function notebook(rects: Rect[]): SkinDecoration[] {
  if (!rects.length) return []
  const frame = expand(bounds(rects), 0.016, 0.02)
  const result: SkinDecoration[] = [
    { kind: 'fill_box', rect: frame, color_token: 'surface', radius_pt: 8 },
    {
      kind: 'side_line',
      rect: { x: frame.x + 0.038, y: frame.y, w: 0.004, h: frame.h },
      color_token: 'accent_soft',
    },
  ]
  for (let index = 0; index < 4; index += 1) {
    result.push({
      kind: 'timeline_dot',
      rect: {
        x: Math.max(0.002, frame.x - 0.006),
        y: frame.y + (frame.h * (index + 1)) / 5 - 0.008,
        w: 0.012,
        h: 0.016,
      },
      color_token: 'line_strong',
    })
  }
  return result
}

function magazine(rects: Rect[]): SkinDecoration[] {
  if (!rects.length) return []
  const frame = expand(bounds(rects), 0.015, 0.015)
  return [
    {
      kind: 'fill_box',
      rect: { x: frame.x, y: frame.y, w: Math.min(0.13, frame.w), h: frame.h },
      color_token: 'accent_soft',
    },
    {
      kind: 'side_line',
      rect: { x: frame.x, y: frame.y, w: 0.008, h: frame.h },
      color_token: 'accent',
    },
    {
      kind: 'side_line',
      rect: { x: frame.x, y: frame.y, w: frame.w, h: 0.006 },
      color_token: 'line_strong',
    },
  ]
}

function panel(rects: Rect[]): SkinDecoration[] {
  if (!rects.length) return []
  const frame = expand(bounds(rects), 0.02, 0.025)
  const inner = expand(bounds(rects), 0.008, 0.012)
  return [
    {
      kind: 'outline_box',
      rect: frame,
      color_token: 'line_strong',
      radius_pt: 6,
    },
    { kind: 'outline_box', rect: inner, color_token: 'line', radius_pt: 4 },
    {
      kind: 'fill_box',
      rect: { x: frame.x + 0.025, y: frame.y, w: 0.11, h: 0.012 },
      color_token: 'accent',
      radius_pt: 3,
    },
  ]
}

function clean(rects: Rect[]): SkinDecoration[] {
  if (!rects.length) return []
  const title = [...rects].sort((a, b) => a.y - b.y)[0]
  return [
    {
      kind: 'side_line',
      rect: {
        x: title.x,
        y: Math.min(0.94, title.y + title.h + 0.018),
        w: Math.min(0.16, title.w),
        h: 0.005,
      },
      color_token: 'accent',
    },
  ]
}

function bounds(rects: Rect[]): Rect {
  const x = Math.min(...rects.map((rect) => rect.x))
  const y = Math.min(...rects.map((rect) => rect.y))
  const right = Math.max(...rects.map((rect) => rect.x + rect.w))
  const bottom = Math.max(...rects.map((rect) => rect.y + rect.h))
  return { x, y, w: right - x, h: bottom - y }
}
