import { resolveColor } from '@/render/style'
import { CANVAS_HEIGHT_PT, CANVAS_WIDTH_PT, type Rect, type Theme } from '@/render/types'

/** 与 backend/app/domain/ambient.py 对齐 */

export type AmbientScope = 'cover' | 'section' | 'content'

export type AmbientShape = {
  kind: 'rect' | 'round_rect' | 'ellipse' | 'text'
  rect: Rect
  color: string
  text?: string | null
  font?: 'display' | 'body' | null
  size_pt?: number | null
  weight?: number | null
  letter_spacing_pt?: number
  align?: 'left' | 'center' | 'right'
  rotation?: number
}

type MotifBase = {
  scope?: AmbientScope[] | null
  color?: string
  strength?: number
  avoid_content?: boolean
}

export type AmbientMotif = MotifBase &
  (
    | {
        motif: 'edge_band'
        edge?: 'top' | 'bottom' | 'left' | 'right'
        thickness_pt?: number
        start?: number
        end?: number
      }
    | {
        motif: 'corner_bracket'
        corner?: 'top_left' | 'top_right' | 'bottom_left' | 'bottom_right'
        size_pt?: number
        thickness_pt?: number
        inset_pt?: number
      }
    | {
        motif: 'hairline_grid'
        columns?: number
        rows?: number
        thickness_pt?: number
        area?: Rect | null
      }
    | { motif: 'glow'; cx?: number; cy?: number; radius_pt?: number; layers?: number }
    | {
        motif: 'watermark'
        rect: Rect
        text?: string | null
        size_pt?: number
        font?: 'display' | 'body'
        weight?: number
        letter_spacing_pt?: number
        align?: 'left' | 'center' | 'right'
      }
    | {
        motif: 'scatter'
        symbol?: 'petal' | 'spark' | 'dot' | 'diamond' | 'dash' | 'chip'
        count?: number
        seed?: number
        area?: Rect
        min_size_pt?: number
        max_size_pt?: number
      }
    | {
        motif: 'orbit'
        cx?: number
        cy?: number
        radius_x_pt?: number
        radius_y_pt?: number
        nodes?: number
        dot_size_pt?: number
        start_deg?: number
      }
    | {
        motif: 'sticker'
        rect: Rect
        text: string
        size_pt?: number
        font?: 'display' | 'body'
        weight?: number
        align?: 'left' | 'center' | 'right'
        rotation?: number
        text_color?: string
      }
    | {
        motif: 'frame'
        inset_pt?: number
        thickness_pt?: number
        corner_size_pt?: number
      }
    | {
        motif: 'stripe_field'
        area?: Rect
        count?: number
        thickness_pt?: number
        gap_pt?: number
        rotation?: number
      }
  )

const SCOPE_BY_LAYOUT: Record<string, AmbientScope> = { cover: 'cover', section: 'section' }
const FULL_CANVAS: Rect = { x: 0, y: 0, w: 1, h: 1 }

/** 与后端 AVOID_OVERLAP_TOLERANCE 一致 */
const AVOID_OVERLAP_TOLERANCE = 0.05

export function scopeOf(layoutId: string): AmbientScope {
  return SCOPE_BY_LAYOUT[layoutId] ?? 'content'
}

/**
 * 展开当前主题在这一页上的氛围层图元，按声明顺序自下而上。
 *
 * occupied 是本页内容块占的位置，供 avoid_content 母题避让；不传就是不避让。
 */
export function iterAmbientShapes(
  theme: Theme,
  layoutId: string,
  slideIndex = 0,
  occupied: readonly Rect[] = [],
): AmbientShape[] {
  const motifs = theme.ambient
  if (!motifs?.length) return []

  const scope = scopeOf(layoutId)
  const background = resolveColor(theme, 'background')
  const shapes: AmbientShape[] = []

  for (const motif of motifs) {
    if (motif.scope && !motif.scope.includes(scope)) continue
    const drawn = expand(motif, theme, background, slideIndex)
    shapes.push(...(motif.avoid_content ? keepClear(drawn, occupied) : drawn))
  }
  return shapes
}

function expand(
  motif: AmbientMotif,
  theme: Theme,
  background: string,
  slideIndex: number,
): AmbientShape[] {
  const base = resolveColor(theme, motif.color ?? 'accent')
  const strength = motif.strength ?? 0.2
  const color = mixHex(base, background, strength)
  switch (motif.motif) {
    case 'edge_band':
      return edgeBand(motif, color)
    case 'corner_bracket':
      return cornerBracket(motif, color)
    case 'hairline_grid':
      return hairlineGrid(motif, color)
    case 'glow':
      // 光晕自己按层混色，拿的是原色而非混好的 color
      return glow(motif, base, background, strength)
    case 'watermark':
      return watermark(motif, color, slideIndex)
    case 'scatter':
      return scatter(motif, color, slideIndex)
    case 'orbit':
      return orbit(motif, color)
    case 'sticker':
      return sticker(motif, color, resolveColor(theme, motif.text_color ?? 'background'))
    case 'frame':
      return frameMotif(motif, color)
    case 'stripe_field':
      return stripeField(motif, color)
  }
}

/**
 * 丢掉压在内容上的图元。
 *
 * 逐图元判定而非整只母题判定，网格才能只保留落在栏间空隙的那几条线。
 */
function keepClear(shapes: AmbientShape[], occupied: readonly Rect[]): AmbientShape[] {
  if (!occupied.length) return shapes
  return shapes.filter((shape) => coveredRatio(shape.rect, occupied) <= AVOID_OVERLAP_TOLERANCE)
}

function coveredRatio(rect: Rect, occupied: readonly Rect[]): number {
  const area = rect.w * rect.h
  if (area <= 0) return 0
  let covered = 0
  for (const other of occupied) covered += overlapArea(rect, other)
  return covered / area
}

function overlapArea(a: Rect, b: Rect): number {
  const width = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)
  const height = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y)
  if (width <= 0 || height <= 0) return 0
  return width * height
}

type EdgeBand = Extract<AmbientMotif, { motif: 'edge_band' }>
type CornerBracket = Extract<AmbientMotif, { motif: 'corner_bracket' }>
type HairlineGrid = Extract<AmbientMotif, { motif: 'hairline_grid' }>
type Glow = Extract<AmbientMotif, { motif: 'glow' }>
type Watermark = Extract<AmbientMotif, { motif: 'watermark' }>
type Scatter = Extract<AmbientMotif, { motif: 'scatter' }>
type Orbit = Extract<AmbientMotif, { motif: 'orbit' }>
type Sticker = Extract<AmbientMotif, { motif: 'sticker' }>
type FrameMotif = Extract<AmbientMotif, { motif: 'frame' }>
type StripeField = Extract<AmbientMotif, { motif: 'stripe_field' }>

function edgeBand(motif: EdgeBand, color: string): AmbientShape[] {
  const [start, end] = [motif.start ?? 0, motif.end ?? 1].sort((a, b) => a - b) as [number, number]
  const span = end - start
  if (span <= 0) return []

  const edge = motif.edge ?? 'left'
  const thickness = motif.thickness_pt ?? 6
  if (edge === 'left' || edge === 'right') {
    const w = thickness / CANVAS_WIDTH_PT
    return fill(edge === 'left' ? 0 : 1 - w, start, w, span, color)
  }
  const h = thickness / CANVAS_HEIGHT_PT
  return fill(start, edge === 'top' ? 0 : 1 - h, span, h, color)
}

function cornerBracket(motif: CornerBracket, color: string): AmbientShape[] {
  const corner = motif.corner ?? 'top_right'
  const size = motif.size_pt ?? 88
  const thickness = motif.thickness_pt ?? 1.5
  const inset = motif.inset_pt ?? 22

  const insetX = inset / CANVAS_WIDTH_PT
  const insetY = inset / CANVAS_HEIGHT_PT
  const armX = size / CANVAS_WIDTH_PT
  const armY = size / CANVAS_HEIGHT_PT
  const thickX = thickness / CANVAS_WIDTH_PT
  const thickY = thickness / CANVAS_HEIGHT_PT

  const left = corner.includes('left')
  const top = corner.includes('top')
  const x0 = left ? insetX : 1 - insetX - armX
  const y0 = top ? insetY : 1 - insetY - armY
  const armVerticalX = left ? x0 : x0 + armX - thickX
  const armHorizontalY = top ? y0 : y0 + armY - thickY

  return [
    ...fill(x0, armHorizontalY, armX, thickY, color),
    ...fill(armVerticalX, y0, thickX, armY, color),
  ]
}

function hairlineGrid(motif: HairlineGrid, color: string): AmbientShape[] {
  const area = motif.area ?? FULL_CANVAS
  const thickness = motif.thickness_pt ?? 0.75
  const w = thickness / CANVAS_WIDTH_PT
  const h = thickness / CANVAS_HEIGHT_PT

  const shapes: AmbientShape[] = []
  for (let index = 1; index < (motif.columns ?? 0); index += 1) {
    const x = area.x + (area.w * index) / (motif.columns ?? 1)
    shapes.push(...fill(x - w / 2, area.y, w, area.h, color))
  }
  for (let index = 1; index < (motif.rows ?? 0); index += 1) {
    const y = area.y + (area.h * index) / (motif.rows ?? 1)
    shapes.push(...fill(area.x, y - h / 2, area.w, h, color))
  }
  return shapes
}

function glow(motif: Glow, base: string, background: string, strength: number): AmbientShape[] {
  const cx = motif.cx ?? 0.85
  const cy = motif.cy ?? 0.16
  const radius = motif.radius_pt ?? 320
  const layers = motif.layers ?? 4

  const shapes: AmbientShape[] = []
  for (let index = 0; index < layers; index += 1) {
    const scale = (layers - index) / layers
    const ratio = (strength * (index + 1)) / layers
    const rx = (radius * scale) / CANVAS_WIDTH_PT
    const ry = (radius * scale) / CANVAS_HEIGHT_PT
    shapes.push(
      ...fill(cx - rx, cy - ry, rx * 2, ry * 2, mixHex(base, background, ratio), 'ellipse'),
    )
  }
  return shapes
}

function watermark(motif: Watermark, color: string, slideIndex: number): AmbientShape[] {
  return [
    {
      kind: 'text',
      rect: motif.rect,
      color,
      text: motif.text ? motif.text : String(slideIndex + 1).padStart(2, '0'),
      font: motif.font ?? 'display',
      size_pt: motif.size_pt ?? 180,
      weight: motif.weight ?? 700,
      letter_spacing_pt: motif.letter_spacing_pt ?? 0,
      align: motif.align ?? 'left',
    },
  ]
}

function randomValues(seed: number): () => number {
  let state = seed >>> 0
  return () => {
    state = (Math.imul(1664525, state) + 1013904223) >>> 0
    return state / 4294967296
  }
}

function scatter(motif: Scatter, color: string, slideIndex: number): AmbientShape[] {
  const rand = randomValues((motif.seed ?? 17) + slideIndex * 7919)
  const [low, high] = [motif.min_size_pt ?? 4, motif.max_size_pt ?? 12].sort((a, b) => a - b)
  const area = motif.area ?? FULL_CANVAS
  const shapes: AmbientShape[] = []
  for (let index = 0; index < (motif.count ?? 12); index += 1) {
    const size = low + rand() * (high - low)
    const x = area.x + rand() * area.w
    const y = area.y + rand() * area.h
    const rotation = rand() * 180 - 90
    const w = size / CANVAS_WIDTH_PT
    const h = size / CANVAS_HEIGHT_PT
    switch (motif.symbol ?? 'dot') {
      case 'petal':
        shapes.push(...fill(x - w / 2, y - h * 0.75, w, h * 1.5, color, 'ellipse', rotation))
        break
      case 'dot':
        shapes.push(...fill(x - w / 2, y - h / 2, w, h, color, 'ellipse'))
        break
      case 'diamond':
        shapes.push(...fill(x - w / 2, y - h / 2, w, h, color, 'round_rect', 45 + rotation * 0.15))
        break
      case 'dash':
        shapes.push(...fill(x - w, y - h * 0.18, w * 2, h * 0.36, color, 'round_rect', rotation))
        break
      case 'chip':
        shapes.push(...fill(x - w / 2, y - h / 2, w, h, color, 'round_rect', rotation * 0.2))
        shapes.push(...fill(x - w * 0.12, y - h * 0.12, w * 0.24, h * 0.24, color))
        break
      case 'spark':
        shapes.push(...fill(x - w, y - h * 0.12, w * 2, h * 0.24, color, 'round_rect', rotation))
        shapes.push(...fill(x - w * 0.12, y - h, w * 0.24, h * 2, color, 'round_rect', rotation))
        shapes.push(...fill(x - w * 0.2, y - h * 0.2, w * 0.4, h * 0.4, color, 'ellipse'))
        break
    }
  }
  return shapes
}

function orbit(motif: Orbit, color: string): AmbientShape[] {
  const shapes: AmbientShape[] = []
  const rx = (motif.radius_x_pt ?? 120) / CANVAS_WIDTH_PT
  const ry = (motif.radius_y_pt ?? 72) / CANVAS_HEIGHT_PT
  const dotW = (motif.dot_size_pt ?? 3) / CANVAS_WIDTH_PT
  const dotH = (motif.dot_size_pt ?? 3) / CANVAS_HEIGHT_PT
  const nodes = motif.nodes ?? 18
  const start = ((motif.start_deg ?? 0) * Math.PI) / 180
  for (let index = 0; index < nodes; index += 1) {
    const angle = start + (Math.PI * 2 * index) / nodes
    const x = (motif.cx ?? 0.82) + Math.cos(angle) * rx
    const y = (motif.cy ?? 0.2) + Math.sin(angle) * ry
    const scale = index % 5 === 0 ? 1.8 : 1
    shapes.push(...fill(x - (dotW * scale) / 2, y - (dotH * scale) / 2, dotW * scale, dotH * scale, color, 'ellipse'))
  }
  return shapes
}

function sticker(motif: Sticker, color: string, textColor: string): AmbientShape[] {
  return [
    { kind: 'round_rect', rect: motif.rect, color, rotation: motif.rotation ?? 0 },
    {
      kind: 'text',
      rect: motif.rect,
      color: textColor,
      text: motif.text,
      font: motif.font ?? 'body',
      size_pt: motif.size_pt ?? 11,
      weight: motif.weight ?? 700,
      align: motif.align ?? 'center',
      rotation: motif.rotation ?? 0,
    },
  ]
}

function frameMotif(motif: FrameMotif, color: string): AmbientShape[] {
  const ix = (motif.inset_pt ?? 24) / CANVAS_WIDTH_PT
  const iy = (motif.inset_pt ?? 24) / CANVAS_HEIGHT_PT
  const tx = (motif.thickness_pt ?? 1) / CANVAS_WIDTH_PT
  const ty = (motif.thickness_pt ?? 1) / CANVAS_HEIGHT_PT
  const cx = (motif.corner_size_pt ?? 18) / CANVAS_WIDTH_PT
  const cy = (motif.corner_size_pt ?? 18) / CANVAS_HEIGHT_PT
  const width = Math.max(0, 1 - 2 * ix)
  const height = Math.max(0, 1 - 2 * iy)
  const shapes = [
    ...fill(ix, iy, width, ty, color),
    ...fill(ix, 1 - iy - ty, width, ty, color),
    ...fill(ix, iy, tx, height, color),
    ...fill(1 - ix - tx, iy, tx, height, color),
  ]
  for (const [x, y] of [[ix, iy], [1 - ix - cx, iy], [ix, 1 - iy - cy], [1 - ix - cx, 1 - iy - cy]]) {
    shapes.push(...fill(x, y, cx, cy, color, 'round_rect'))
  }
  return shapes
}

function stripeField(motif: StripeField, color: string): AmbientShape[] {
  const shapes: AmbientShape[] = []
  const area = motif.area ?? FULL_CANVAS
  const count = motif.count ?? 5
  const thickness = (motif.thickness_pt ?? 8) / CANVAS_HEIGHT_PT
  const gap = (motif.gap_pt ?? 14) / CANVAS_HEIGHT_PT
  const total = count * thickness + Math.max(0, count - 1) * gap
  const start = area.y + (area.h - total) / 2
  for (let index = 0; index < count; index += 1) {
    shapes.push(...fill(area.x, start + index * (thickness + gap), area.w, thickness, color, 'round_rect', motif.rotation ?? -12))
  }
  return shapes
}

function fill(
  x: number,
  y: number,
  w: number,
  h: number,
  color: string,
  kind: 'rect' | 'round_rect' | 'ellipse' = 'rect',
  rotation = 0,
): AmbientShape[] {
  const rect = kind === 'ellipse' ? bleed(x, y, w, h) : clip(x, y, w, h)
  return rect ? [{ kind, rect, color, rotation }] : []
}

/** 矩形按画布收边。轴对齐矩形的外接框求交就是它自己的裁剪，几何无损。 */
function clip(x: number, y: number, w: number, h: number): Rect | null {
  const left = Math.max(0, x)
  const top = Math.max(0, y)
  const right = Math.min(1, x + w)
  const bottom = Math.min(1, y + h)
  if (right <= left || bottom <= top) return null
  return { x: left, y: top, w: right - left, h: bottom - top }
}

/**
 * 保留原几何，只丢掉完全落在画布外的图元。
 *
 * 椭圆不能按外接框收边：那等于把它压扁，本该同心的几层光晕会变成一串偏心月牙。
 * 让它原样出血，Web 靠根容器 overflow、PPTX 靠幻灯片边界裁。
 */
function bleed(x: number, y: number, w: number, h: number): Rect | null {
  if (x + w <= 0 || y + h <= 0 || x >= 1 || y >= 1) return null
  return { x, y, w, h }
}

/** 与后端 domain/color.mix_hex 逐通道对齐，含 Python round 的「四舍六入五取偶」 */
export function mixHex(foreground: string, background: string, ratio: number): string {
  const clamped = Math.min(1, Math.max(0, ratio))
  const fg = foreground.replace('#', '')
  const bg = background.replace('#', '')
  let out = '#'
  for (const offset of [0, 2, 4]) {
    const value =
      parseInt(fg.slice(offset, offset + 2), 16) * clamped +
      parseInt(bg.slice(offset, offset + 2), 16) * (1 - clamped)
    out += roundHalfEven(value).toString(16).toUpperCase().padStart(2, '0')
  }
  return out
}

function roundHalfEven(value: number): number {
  const floor = Math.floor(value)
  const rest = value - floor
  if (rest > 0.5) return floor + 1
  if (rest < 0.5) return floor
  return floor % 2 === 0 ? floor : floor + 1
}
