import { normalizeGrows } from '@/features/deck/flexNormalize'
import {
  applyVerticalResizeDrag,
  ensureResizePair,
  findContainerById,
  isSpacer,
  ratiosFromDividerDrag,
  setLeafOffset,
  updateRowRatios,
  type DropTarget,
  type ResizeSide,
} from '@/features/deck/flexTree'
import type { InsertDragPayload } from '@/features/deck/slideSaveBridge'
import { solveNodeAreas, type FlexContainer } from '@/render/flexLayout'
import { CANVAS_HEIGHT_PT, CANVAS_WIDTH_PT } from '@/render/types'

/** 横向拉伸所需的行内分隔线定位 */
export type RatioAxis = {
  rowId: string
  leftIndex: number
  rowX: number
  rowW: number
}

/** 纵向拉伸所需的列内分隔线定位 */
export type GrowAxis = {
  columnId: string
  topIndex: number
  colY: number
  colH: number
}

/** 块边缩放：pointerdown 可先补占位，但需越过阈值才 preview/commit */
export type ResizeGate = {
  activated: boolean
  deferPreview: boolean
  startClientX: number
  startClientY: number
  /**
   * 四角双轴拖：越过激活阈值时按主方向锁定。
   * 上下为主则忽略横向，避免竖直拉缩时左右抖动改宽度。
   */
  axisLock?: 'x' | 'y' | 'both'
}

export type RatioDragAxis = RatioAxis & { startT: number; originX: number }
export type GrowDragAxis = GrowAxis & { startT: number; originY: number }

export type DragSession =
  | {
      kind: 'reorder'
      blockId: string
      drop: DropTarget | null
      grabOffsetX: number
      grabOffsetY: number
      ghostW: number
      ghostH: number
      pointerX: number
      pointerY: number
    }
  | {
      kind: 'insert'
      payload: InsertDragPayload
      drop: DropTarget | null
      grabOffsetX: number
      grabOffsetY: number
      ghostW: number
      ghostH: number
      pointerX: number
      pointerY: number
      activated: boolean
      startClientX: number
      startClientY: number
    }
  | ({ kind: 'ratio'; baseTree: FlexContainer } & RatioDragAxis & ResizeGate)
  | ({
      kind: 'grow'
      baseTree: FlexContainer
      /** 角点按下时只补纵向拉伸对；激活后若主轴含横向再补宽度对 */
      pendingCorner?: {
        blockId: string
        sideX: ResizeSide
        originX: number
      }
    } & GrowDragAxis &
      ResizeGate)
  | {
      kind: 'box'
      baseTree: FlexContainer
      x: RatioDragAxis
      y: GrowDragAxis
    } & ResizeGate
  | {
      kind: 'offset'
      blockId: string
      baseTree: FlexContainer
      baseX: number
      baseY: number
      startX: number
      startY: number
    }

export type ResizeDragSession = Extract<DragSession, { kind: 'ratio' | 'grow' | 'box' }>

export function ratioStartT(ratios: number[], leftIndex: number): number {
  let prefix = 0
  for (let i = 0; i <= leftIndex; i++) prefix += ratios[i] ?? 0
  return prefix / 100
}

export function growStartT(grows: number[], topIndex: number): number {
  const total = grows.reduce((a, b) => a + b, 0)
  if (total <= 0) return 0.5
  let prefix = 0
  for (let i = 0; i <= topIndex; i++) prefix += grows[i] ?? 0
  return prefix / total
}

/** 内容侧保底；spacer 侧为 0，才能拖回通栏/满高原位 */
const CONTENT_SIDE_MIN = 0.05

/** 按行内分隔线拖拽结果重算 ratios（相对 startT，避免首帧跳变） */
function applyRatioDrag(base: FlexContainer, axis: RatioDragAxis, pointerX: number) {
  const row = findContainerById(base, axis.rowId)
  if (!row || row.type !== 'row') return null
  const ratios =
    row.ratios?.length === row.children.length
      ? [...row.ratios]
      : Array.from({ length: row.children.length }, () => 100 / row.children.length)
  const left = row.children[axis.leftIndex]
  const right = row.children[axis.leftIndex + 1]
  const next = ratiosFromDividerDrag({
    ratios,
    leftIndex: axis.leftIndex,
    t: axis.startT + (pointerX - axis.originX) / Math.max(axis.rowW, 1e-9),
    minLeft: left && isSpacer(left) ? 0 : CONTENT_SIDE_MIN,
    minRight: right && isSpacer(right) ? 0 : CONTENT_SIDE_MIN,
  })
  return updateRowRatios(base, axis.rowId, next)
}

/** 按列内分隔线拖拽；缺侧 wrap 外扩时上收父列 grow */
function applyGrowDrag(base: FlexContainer, axis: GrowDragAxis, pointerY: number) {
  return applyVerticalResizeDrag({
    root: base,
    columnId: axis.columnId,
    topIndex: axis.topIndex,
    colH: axis.colH,
    startT: axis.startT,
    originY: axis.originY,
    pointerY,
  })
}

/**
 * 把一次指针移动折算成新的布局树；reorder 不重排预览，返回 null。
 * 出口统一归一 grow：预览即保存后的最终形态，松手不再跳。
 */
export function resolveDragTree(
  session: DragSession,
  pointer: { x: number; y: number },
): FlexContainer | null {
  const next = dragTreeDraft(session, pointer)
  return next ? normalizeGrows(next) : null
}

function dragTreeDraft(
  session: DragSession,
  pointer: { x: number; y: number },
): FlexContainer | null {
  switch (session.kind) {
    case 'ratio':
      return applyRatioDrag(session.baseTree, session, pointer.x)
    case 'grow':
      return applyGrowDrag(session.baseTree, session, pointer.y)
    case 'box': {
      const lock = session.axisLock ?? 'both'
      let tree = session.baseTree
      if (lock === 'x' || lock === 'both') {
        tree = applyRatioDrag(tree, session.x, pointer.x) ?? tree
      }
      if (lock === 'y' || lock === 'both') {
        tree = applyGrowDrag(tree, session.y, pointer.y) ?? tree
      }
      return tree
    }
    case 'offset':
      return setLeafOffset(
        session.baseTree,
        session.blockId,
        session.baseX + (pointer.x - session.startX) * CANVAS_WIDTH_PT,
        session.baseY + (pointer.y - session.startY) * CANVAS_HEIGHT_PT,
      )
    default:
      return null
  }
}

function rowSpanOf(
  baseTree: FlexContainer,
  rowId: string,
): { rowX: number; rowW: number } | null {
  const rowArea = solveNodeAreas(baseTree).get(rowId)
  if (rowArea && rowArea.w > 0) return { rowX: rowArea.x, rowW: rowArea.w }
  return null
}

/**
 * 角点拖激活：主轴为 Y 时保持纯纵向 grow；
 * 含横向时再补宽度拉伸对，升为 box / ratio。
 */
export function activateCornerGrow(
  session: Extract<DragSession, { kind: 'grow' }>,
  lock: 'x' | 'y' | 'both',
): ResizeDragSession {
  const pending = session.pendingCorner
  if (!pending) {
    return { ...session, activated: true, pendingCorner: undefined }
  }
  if (lock === 'y') {
    return {
      ...session,
      activated: true,
      pendingCorner: undefined,
      axisLock: 'y',
    }
  }

  const ensuredX = ensureResizePair(session.baseTree, pending.blockId, 'x', pending.sideX)
  if (!ensuredX) {
    return {
      ...session,
      activated: true,
      pendingCorner: undefined,
      axisLock: 'y',
    }
  }
  const xSpan = rowSpanOf(ensuredX.tree, ensuredX.containerId)
  const row = findContainerById(ensuredX.tree, ensuredX.containerId)
  if (!xSpan || !row || row.type !== 'row') {
    return {
      ...session,
      activated: true,
      pendingCorner: undefined,
      axisLock: 'y',
    }
  }
  const ratios =
    row.ratios?.length === row.children.length
      ? [...row.ratios]
      : Array.from({ length: row.children.length }, () => 100 / row.children.length)
  const xAxis: RatioDragAxis = {
    rowId: ensuredX.containerId,
    leftIndex: ensuredX.index,
    rowX: xSpan.rowX,
    rowW: xSpan.rowW,
    startT: ratioStartT(ratios, ensuredX.index),
    originX: pending.originX,
  }

  if (lock === 'x') {
    return {
      kind: 'ratio',
      baseTree: ensuredX.tree,
      ...xAxis,
      activated: true,
      deferPreview: true,
      startClientX: session.startClientX,
      startClientY: session.startClientY,
      axisLock: 'x',
    }
  }

  const column = findContainerById(ensuredX.tree, session.columnId)
  if (!column || column.type !== 'column') {
    return {
      kind: 'ratio',
      baseTree: ensuredX.tree,
      ...xAxis,
      activated: true,
      deferPreview: true,
      startClientX: session.startClientX,
      startClientY: session.startClientY,
      axisLock: 'x',
    }
  }
  const grows = column.children.map((child) => child.grow ?? 1)
  return {
    kind: 'box',
    baseTree: ensuredX.tree,
    x: xAxis,
    y: {
      columnId: session.columnId,
      topIndex: session.topIndex,
      colY: session.colY,
      colH: session.colH,
      startT: growStartT(grows, session.topIndex),
      originY: session.originY,
    },
    activated: true,
    deferPreview: true,
    startClientX: session.startClientX,
    startClientY: session.startClientY,
    axisLock: 'both',
  }
}
