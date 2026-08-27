import { CANVAS_HEIGHT_PT, CANVAS_WIDTH_PT, SAFE_AREA, type Rect } from './types'

export type GroupPreset =
  | 'solid_boxes'
  | 'outline_boxes'
  | 'side_line'
  | 'numbered_steps'
  | 'timeline'

export type FlexContainer = {
  type: 'row' | 'column'
  id: string
  children: FlexNode[]
  gap_pt?: number
  ratios?: number[] | null
  preset?: GroupPreset | null
  grow?: number
}

export type FlexLeaf = {
  type: 'block'
  id: string
  block_id: string
  grow?: number
  text_style?: string | null
  /** 相对 solver 结果的像素级平移，只挪位置不改尺寸；solver 会钳制在画布内 */
  offset_x_pt?: number
  offset_y_pt?: number
  /** 出血：贴着安全区边界的方向扩展到画布边缘，只给图片/图表用 */
  bleed?: boolean
}

export type FlexNode = FlexContainer | FlexLeaf

export type PlacedBlock = {
  block_id: string
  rect: Rect
  text_style?: string | null
}

export type SkinFrame = {
  container_id: string
  preset: GroupPreset
  child_index: number
  rect: Rect
}

/** 与 backend/app/domain/flex_layout.py PRESET_INSET_PT 保持一致 */
export const PRESET_INSET_PT: Record<GroupPreset, number> = {
  solid_boxes: 12.0,
  outline_boxes: 12.0,
  side_line: 16.0,
  numbered_steps: 20.0,
  timeline: 16.0,
}

const DEFAULT_GAP_PT = 16.0
const DEFAULT_GROW = 1.0

/** 判定叶子是否贴着安全区某条边的容差，约合 2pt；与后端 _EDGE_EPS 一致 */
const EDGE_EPS = 0.0025

function isLeaf(node: FlexNode): node is FlexLeaf {
  return node.type === 'block'
}

/** 将 FlexContainer 树递归求解为归一化矩形列表；浮点路径对齐 Python solver。 */
export function solve(root: FlexContainer, canvas?: Rect): PlacedBlock[] {
  return solveWithFrames(root, canvas).placed
}

/** 每个节点（含空 spacer 容器）的分配矩形，供拉伸手柄使用 */
export function solveNodeAreas(
  root: FlexContainer,
  canvas?: Rect,
): Map<string, Rect> {
  const areas = new Map<string, Rect>()
  const walk = (node: FlexContainer, area: Rect) => {
    areas.set(node.id, area)
    if (!node.children.length) return
    const childAreas = splitArea(node, area)
    for (let i = 0; i < node.children.length; i++) {
      const child = node.children[i]!
      const content = applyPresetInset(node, childAreas[i]!)
      if (isLeaf(child)) {
        areas.set(child.id, applyOffset(applyBleed(content, child), child))
      } else {
        walk(child, content)
      }
    }
  }
  walk(root, canvas ?? SAFE_AREA)
  return areas
}

export function solveWithFrames(
  root: FlexContainer,
  canvas?: Rect,
): { placed: PlacedBlock[]; frames: SkinFrame[] } {
  const area = canvas ?? SAFE_AREA
  const frames: SkinFrame[] = []
  const placed = solveContainer(root, area, frames)
  return { placed, frames }
}

function solveContainer(
  node: FlexContainer,
  area: Rect,
  frames: SkinFrame[],
): PlacedBlock[] {
  const children = node.children
  if (!children.length) return []

  const childAreas = splitArea(node, area)
  const placed: PlacedBlock[] = []
  for (let i = 0; i < children.length; i++) {
    const childArea = childAreas[i]!
    if (node.preset != null) {
      frames.push({
        container_id: node.id,
        preset: node.preset,
        child_index: i,
        rect: childArea,
      })
    }
    const content = applyPresetInset(node, childArea)
    placed.push(...solveNode(children[i]!, content, frames))
  }
  return placed
}

function solveNode(node: FlexNode, area: Rect, frames: SkinFrame[]): PlacedBlock[] {
  if (isLeaf(node)) {
    return [
      {
        block_id: node.block_id,
        rect: applyOffset(applyBleed(area, node), node),
        text_style: node.text_style,
      },
    ]
  }
  return solveContainer(node, area, frames)
}

/**
 * 出血：把贴着安全区边界的叶子扩展到画布边缘。
 * 与 backend/app/domain/flex_solve.py 的 _apply_bleed 保持一致。
 */
function applyBleed(area: Rect, leaf: FlexLeaf): Rect {
  if (!leaf.bleed) return area
  const areaRight = area.x + area.w
  const areaBottom = area.y + area.h
  const safeRight = SAFE_AREA.x + SAFE_AREA.w
  const safeBottom = SAFE_AREA.y + SAFE_AREA.h
  const left = area.x - SAFE_AREA.x <= EDGE_EPS ? 0.0 : area.x
  const top = area.y - SAFE_AREA.y <= EDGE_EPS ? 0.0 : area.y
  const right = safeRight - areaRight <= EDGE_EPS ? 1.0 : areaRight
  const bottom = safeBottom - areaBottom <= EDGE_EPS ? 1.0 : areaBottom
  return { x: left, y: top, w: right - left, h: bottom - top }
}

/**
 * 应用叶子的像素级平移，并钳制在画布内。
 * 与 backend/app/domain/flex_solve.py 的 _apply_offset 保持一致。
 */
function applyOffset(area: Rect, leaf: FlexLeaf): Rect {
  const dxPt = leaf.offset_x_pt ?? 0
  const dyPt = leaf.offset_y_pt ?? 0
  if (!dxPt && !dyPt) return area
  return {
    x: clampStart(area.x + dxPt / CANVAS_WIDTH_PT, area.w),
    y: clampStart(area.y + dyPt / CANVAS_HEIGHT_PT, area.h),
    w: area.w,
    h: area.h,
  }
}

function clampStart(start: number, extent: number): number {
  return Math.min(Math.max(start, 0.0), Math.max(1.0 - extent, 0.0))
}

/**
 * 返回 [单个间隙, 间隙总量]；间隙总量超过可用长度时按比例压缩。
 * 与 backend/app/domain/flex_solve.py 的 _fit_gaps 保持一致。
 */
function fitGaps(gapNorm: number, n: number, extent: number): [number, number] {
  if (n <= 1 || gapNorm <= 0.0) return [0.0, 0.0]
  const total = (n - 1) * gapNorm
  if (total <= extent) return [gapNorm, total]
  if (extent <= 0.0) return [0.0, 0.0]
  return [extent / (n - 1), extent]
}

function splitArea(node: FlexContainer, area: Rect): Rect[] {
  const n = node.children.length
  if (n === 0) return []

  const gapPt = node.gap_pt ?? DEFAULT_GAP_PT

  if (node.type === 'row') {
    const [gapNorm, totalGap] = fitGaps(gapPt / CANVAS_WIDTH_PT, n, area.w)
    const weights = rowWeights(node.ratios, n)
    const totalW = Math.max(area.w - totalGap, 0.0)
    const end = area.x + area.w
    let cursor = area.x
    const rects: Rect[] = []
    for (let index = 0; index < weights.length; index++) {
      // 末项贴紧父区域右缘，吸收浮点残差
      const w = index === n - 1 ? end - cursor : totalW * weights[index]!
      rects.push({ x: cursor, y: area.y, w: Math.max(w, 1e-9), h: area.h })
      cursor += w
      if (index < n - 1) {
        cursor += gapNorm
      }
    }
    return rects
  }

  const [gapNorm, totalGap] = fitGaps(gapPt / CANVAS_HEIGHT_PT, n, area.h)
  const weights = columnWeights(node.children)
  const totalH = Math.max(area.h - totalGap, 0.0)
  const end = area.y + area.h
  let cursor = area.y
  const rects: Rect[] = []
  for (let index = 0; index < weights.length; index++) {
    const h = index === n - 1 ? end - cursor : totalH * weights[index]!
    rects.push({ x: area.x, y: cursor, w: area.w, h: Math.max(h, 1e-9) })
    cursor += h
    if (index < n - 1) {
      cursor += gapNorm
    }
  }
  return rects
}

function rowWeights(ratios: number[] | null | undefined, n: number): number[] {
  if (ratios == null || ratios.length !== n) {
    return Array.from({ length: n }, () => 1.0 / n)
  }
  const total = ratios.reduce((sum, r) => sum + r, 0)
  if (total <= 0) {
    return Array.from({ length: n }, () => 1.0 / n)
  }
  return ratios.map((r) => r / total)
}

function columnWeights(children: FlexNode[]): number[] {
  const grows = children.map((child) => child.grow ?? DEFAULT_GROW)
  const total = grows.reduce((sum, g) => sum + g, 0)
  if (total <= 0) {
    const n = children.length
    return Array.from({ length: n }, () => 1.0 / n)
  }
  return grows.map((g) => g / total)
}

function applyPresetInset(container: FlexContainer, childArea: Rect): Rect {
  if (container.preset == null) return childArea
  const insetPt = PRESET_INSET_PT[container.preset]
  const insetX = insetPt / CANVAS_WIDTH_PT
  const insetY = insetPt / CANVAS_HEIGHT_PT
  const w = childArea.w - 2 * insetX
  const h = childArea.h - 2 * insetY
  if (w <= 0 || h <= 0) return childArea
  return {
    x: childArea.x + insetX,
    y: childArea.y + insetY,
    w,
    h,
  }
}
