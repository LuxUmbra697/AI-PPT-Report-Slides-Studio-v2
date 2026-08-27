import { solveNodeAreas, type FlexContainer } from '@/render/flexLayout'

import type { RectLike } from './constants'
import { NEAREST_SLOT_MAX_DIST } from './constants'
import { nodeBounds } from './geometry'
import {
  findContainerById,
  findContainerParent,
  findLeafParent,
  isContainer,
  isSpacer,
} from './tree'

export type DropTarget = {
  parentId: string
  index: number
  /** 指示线：归一化 */
  line: { x: number; y: number; w: number; h: number; axis: 'x' | 'y' }
}

/**
 * 落点语义：
 * - reorder 是搬动已有块，落到内容前缘最不容易误判
 * - insert 是往空白里放新块，必须能落进尾部空白本身
 */
export type DropMode = 'insert' | 'reorder'

/** 画布内就地插入点：出现在兄弟间隙与首尾 */
export type InsertSlot = {
  parentId: string
  index: number
  /** + 按钮中心，归一化 */
  x: number
  y: number
  axis: 'x' | 'y'
}

/**
 * 收集可插入间隙。
 * 单子容器（常见列包装）不收集，避免空列两侧刷满插槽；
 * insert 模式例外，否则单块列旁的大片空白无处可落。
 * 传入 nodeAreas 后 spacer 空容器也有 bounds，空白区可作落点。
 */
export function collectInsertSlots(
  root: FlexContainer,
  placements: Map<string, RectLike>,
  nodeAreas?: Map<string, RectLike>,
  mode: DropMode = 'reorder',
): InsertSlot[] {
  const areas = nodeAreas ?? solveNodeAreas(root)
  const result: InsertSlot[] = []

  const walk = (node: FlexContainer, isRoot: boolean) => {
    const allow =
      isRoot ||
      node.children.length >= 2 ||
      (mode === 'insert' && node.children.length > 0)
    if (allow) {
      const vertical = node.type === 'column'
      const childBounds = node.children.map((child) =>
        nodeBounds(child, placements, areas),
      )
      const valid = childBounds
        .map((bounds, index) => ({ bounds, index }))
        .filter((item): item is { bounds: RectLike; index: number } => item.bounds != null)

      if (valid.length > 0) {
        const first = valid[0]!
        const last = valid[valid.length - 1]!

        if (vertical) {
          result.push({
            parentId: node.id,
            index: first.index,
            x: first.bounds.x + first.bounds.w / 2,
            y: first.bounds.y,
            axis: 'y',
          })
          for (let i = 0; i < valid.length - 1; i++) {
            const a = valid[i]!
            const b = valid[i + 1]!
            result.push({
              parentId: node.id,
              index: b.index,
              x: (a.bounds.x + a.bounds.w / 2 + b.bounds.x + b.bounds.w / 2) / 2,
              y: (a.bounds.y + a.bounds.h + b.bounds.y) / 2,
              axis: 'y',
            })
          }
          result.push({
            parentId: node.id,
            index: last.index + 1,
            x: last.bounds.x + last.bounds.w / 2,
            y: last.bounds.y + last.bounds.h,
            axis: 'y',
          })
        } else {
          result.push({
            parentId: node.id,
            index: first.index,
            x: first.bounds.x,
            y: first.bounds.y + first.bounds.h / 2,
            axis: 'x',
          })
          for (let i = 0; i < valid.length - 1; i++) {
            const a = valid[i]!
            const b = valid[i + 1]!
            result.push({
              parentId: node.id,
              index: b.index,
              x: (a.bounds.x + a.bounds.w + b.bounds.x) / 2,
              y: (a.bounds.y + a.bounds.h / 2 + b.bounds.y + b.bounds.h / 2) / 2,
              axis: 'x',
            })
          }
          result.push({
            parentId: node.id,
            index: last.index + 1,
            x: last.bounds.x + last.bounds.w,
            y: last.bounds.y + last.bounds.h / 2,
            axis: 'x',
          })
        }
      }
    }

    for (const child of node.children) {
      if (isContainer(child)) walk(child, false)
    }
  }

  walk(root, true)
  return result
}

/**
 * 根据指针位置计算插入点。
 * 1) 命中其它叶子 → 前/后半区
 * 2) 否则取最近插槽（间隙 / spacer / 首尾空白）
 */
export function resolveDropTarget(args: {
  root: FlexContainer
  placements: Map<string, RectLike>
  pointer: { x: number; y: number }
  draggedBlockId?: string | null
  mode?: DropMode
}): DropTarget | null {
  const { root, placements, pointer, draggedBlockId, mode = 'reorder' } = args

  let hitId: string | null = null
  let hitRect: RectLike | null = null
  for (const [blockId, rect] of placements) {
    if (draggedBlockId && blockId === draggedBlockId) continue
    if (
      pointer.x >= rect.x &&
      pointer.x <= rect.x + rect.w &&
      pointer.y >= rect.y &&
      pointer.y <= rect.y + rect.h
    ) {
      hitId = blockId
      hitRect = rect
      break
    }
  }
  if (hitId && hitRect) {
    const loc = findLeafParent(root, hitId)
    if (loc) {
      const vertical = loc.parent.type === 'column'
      let before = vertical
        ? pointer.y < hitRect.y + hitRect.h / 2
        : pointer.x < hitRect.x + hitRect.w / 2
      // 命中末内容下半区且锚定后已是整页末尾：改为插在该块前，线贴其上边界。
      // 真正「插到文末」走块外空白 nearestSlot（线在空位前缘）。
      // insert 例外：块下方空白正是用户想放新块的地方，不能弹回块前。
      if (!before && mode === 'reorder') {
        const peek = resolveDropAnchor(root, loc.parent, loc.index, false, mode)
        if (isDropEof(peek.parent, peek.index)) before = true
      }
      const anchor = resolveDropAnchor(root, loc.parent, loc.index, before, mode)
      const areas = solveNodeAreas(root)
      return {
        parentId: anchor.parent.id,
        index: anchor.index,
        line: dropLineAtIndex(root, anchor.parent, anchor.index, placements, areas),
      }
    }
  }

  return nearestSlotDropTarget(root, placements, pointer, mode)
}

function isDropEof(parent: FlexContainer, index: number): boolean {
  for (let i = index; i < parent.children.length; i++) {
    if (!isSpacer(parent.children[i]!)) return false
  }
  return true
}

/**
 * 将「块前/后」解析为可插入的内容前缘：
 * - 跳过 spacer，避免线落在内容下沿（spacer 顶）
 * - 若「块后」只剩 spacer 直到容器末尾，上收到父级插在该容器之后
 *
 * insert 模式不做这两件事：新块要的就是那片空白，落进 spacer 或留在原容器末尾，
 * 上收会让它变成邻列窄条。
 */
function resolveDropAnchor(
  root: FlexContainer,
  parent: FlexContainer,
  leafIndex: number,
  before: boolean,
  mode: DropMode = 'reorder',
): { parent: FlexContainer; index: number } {
  let host = parent
  let index = before ? leafIndex : leafIndex + 1

  if (mode === 'insert') {
    const spacer = spacerChildAt(host, index)
    if (spacer) return { parent: spacer, index: 0 }
  }

  index = skipSpacersIn(host, index)

  if (!before && index >= host.children.length) {
    if (mode === 'insert') return { parent: host, index }
    // 落在 wrap cell 等「内容+尾部 spacer」末尾时，改为插到父级该 cell 之后
    let outer = findContainerParent(root, host.id)
    while (outer) {
      const nextIndex = skipSpacersIn(outer.parent, outer.index + 1)
      if (nextIndex < outer.parent.children.length || outer.parent.id === root.id) {
        host = outer.parent
        index = nextIndex
        break
      }
      outer = findContainerParent(root, outer.parent.id)
    }
  }

  return { parent: host, index }
}

/** 该位置上的占位容器；插入时它就是用户看到的那片空白 */
function spacerChildAt(parent: FlexContainer, index: number): FlexContainer | null {
  const child = parent.children[index]
  if (!child || !isContainer(child) || !isSpacer(child)) return null
  return child
}

/** 插槽转落点引导线（供插入拖放与重排空白落点共用） */
export function dropTargetFromSlot(
  root: FlexContainer,
  slot: InsertSlot,
  placements: Map<string, RectLike>,
  mode: DropMode = 'reorder',
): DropTarget {
  const parent = findContainerById(root, slot.parentId)
  const areas = solveNodeAreas(root)
  if (!parent) {
    return {
      parentId: slot.parentId,
      index: slot.index,
      line:
        slot.axis === 'y'
          ? { x: slot.x, y: slot.y, w: 0.2, h: 0, axis: 'y' }
          : { x: slot.x, y: slot.y, w: 0, h: 0.2, axis: 'x' },
    }
  }
  // 与 hit 路径一致：slot.index 视为「插到此前一子之后」，走 resolveDropAnchor 上收
  const anchor =
    slot.index <= 0
      ? resolveDropAnchorAtStart(parent, mode)
      : resolveDropAnchor(root, parent, Math.max(0, slot.index - 1), false, mode)

  return {
    parentId: anchor.parent.id,
    index: anchor.index,
    line: dropLineAtIndex(root, anchor.parent, anchor.index, placements, areas),
  }
}

/** 容器首位：insert 时首个 spacer 本身就是可落的空白 */
function resolveDropAnchorAtStart(
  parent: FlexContainer,
  mode: DropMode,
): { parent: FlexContainer; index: number } {
  if (mode === 'insert') {
    const spacer = spacerChildAt(parent, 0)
    if (spacer) return { parent: spacer, index: 0 }
  }
  return { parent, index: skipSpacersIn(parent, 0) }
}

function skipSpacersIn(container: FlexContainer, from: number): number {
  let i = from
  while (i < container.children.length && isSpacer(container.children[i]!)) i++
  return i
}

/**
 * 按 drop index 画前缘线：始终优先后继内容的上/左；
 * 落在整页末尾时，若末子为 spacer 用其顶缘，否则才用末内容底缘（块外空白落点）。
 */
function dropLineAtIndex(
  root: FlexContainer,
  parent: FlexContainer,
  index: number,
  placements: Map<string, RectLike>,
  areas: Map<string, RectLike>,
): DropTarget['line'] {
  const vertical = parent.type === 'column'
  const n = parent.children.length
  const parentArea = areas.get(parent.id)
  if (n === 0) {
    const fallback = parentArea ?? { x: 0, y: 0, w: 0.2, h: 0.2 }
    return vertical
      ? { x: fallback.x, y: fallback.y, w: fallback.w, h: 0, axis: 'y' }
      : { x: fallback.x, y: fallback.y, w: 0, h: fallback.h, axis: 'x' }
  }

  let host = parent
  let at = skipSpacersIn(parent, index)

  // 本容器无后继内容 → 向祖先找下一个非 spacer 兄弟的前缘
  if (at >= host.children.length || isSpacer(host.children[at]!)) {
    let outer = findContainerParent(root, host.id)
    while (outer) {
      const next = skipSpacersIn(outer.parent, outer.index + 1)
      if (next < outer.parent.children.length && !isSpacer(outer.parent.children[next]!)) {
        host = outer.parent
        at = next
        break
      }
      outer = findContainerParent(root, outer.parent.id)
    }
  }

  if (at < host.children.length && !isSpacer(host.children[at]!)) {
    const bounds =
      nodeBounds(host.children[at]!, placements, areas) ??
      parentArea ?? { x: 0, y: 0, w: 0.2, h: 0.2 }
    return vertical
      ? { x: bounds.x, y: bounds.y, w: bounds.w, h: 0, axis: 'y' }
      : { x: bounds.x, y: bounds.y, w: 0, h: bounds.h, axis: 'x' }
  }

  // 整页末尾：优先末尾 spacer 的顶/左（空位前缘），避免贴在文字底边
  const last = host.children[host.children.length - 1]!
  if (isSpacer(last)) {
    const bounds =
      nodeBounds(last, placements, areas) ??
      parentArea ?? { x: 0, y: 0, w: 0.2, h: 0.2 }
    return vertical
      ? { x: bounds.x, y: bounds.y, w: bounds.w, h: 0, axis: 'y' }
      : { x: bounds.x, y: bounds.y, w: 0, h: bounds.h, axis: 'x' }
  }
  const bounds =
    nodeBounds(last, placements, areas) ??
    parentArea ?? { x: 0, y: 0, w: 0.2, h: 0.2 }
  return vertical
    ? { x: bounds.x, y: bounds.y + bounds.h, w: bounds.w, h: 0, axis: 'y' }
    : { x: bounds.x + bounds.w, y: bounds.y, w: 0, h: bounds.h, axis: 'x' }
}

function nearestSlotDropTarget(
  root: FlexContainer,
  placements: Map<string, RectLike>,
  pointer: { x: number; y: number },
  mode: DropMode = 'reorder',
): DropTarget | null {
  const slots = collectInsertSlots(root, placements, undefined, mode)
  if (slots.length === 0) {
    // 整页只有一块时仍允许落到根首/尾
    const rootArea = solveNodeAreas(root).get(root.id)
    if (!rootArea) return null
    const before = root.type === 'column'
      ? pointer.y < rootArea.y + rootArea.h / 2
      : pointer.x < rootArea.x + rootArea.w / 2
    const index = before ? 0 : root.children.length
    const slot: InsertSlot = {
      parentId: root.id,
      index,
      x: root.type === 'column' ? rootArea.x + rootArea.w / 2 : before ? rootArea.x : rootArea.x + rootArea.w,
      y: root.type === 'column' ? (before ? rootArea.y : rootArea.y + rootArea.h) : rootArea.y + rootArea.h / 2,
      axis: root.type === 'column' ? 'y' : 'x',
    }
    return dropTargetFromSlot(root, slot, placements, mode)
  }

  let best: InsertSlot | null = null
  let bestDist = Infinity
  for (const slot of slots) {
    const dx = pointer.x - slot.x
    const dy = pointer.y - slot.y
    const dist = dx * dx + dy * dy
    if (dist < bestDist) {
      bestDist = dist
      best = slot
    }
  }
  if (!best) return null
  // 过远则不吸附，避免整页乱跳；约 25% 画布对角线
  if (bestDist > NEAREST_SLOT_MAX_DIST * NEAREST_SLOT_MAX_DIST) return null
  return dropTargetFromSlot(root, best, placements, mode)
}
