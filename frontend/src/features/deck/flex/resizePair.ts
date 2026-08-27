import type { FlexContainer, FlexLeaf } from '@/render/flexLayout'

import { GROW_MAX, SPACER_SEED_GROW, SPACER_SEED_RATIO } from './constants'
import {
  cloneTree,
  findContainerParent,
  findLeafParent,
  isSpacer,
  makeSpacer,
  newNodeId,
} from './tree'

/** 拉伸方向：after 用右/下手柄，before 用左/上手柄 */
export type ResizeSide = 'before' | 'after'

export type ResizePair = {
  tree: FlexContainer
  containerId: string
  index: number
}

/**
 * 保证选中块在指定轴与指定侧可拉伸：必要时插入占位块或就地包一层容器。
 * 返回用于拖拽的 containerId + 分隔线左侧/上方子项 index，以及改写后的树。
 */
export function ensureResizePair(
  root: FlexContainer,
  blockId: string,
  axis: 'x' | 'y',
  side: ResizeSide = 'after',
): ResizePair | null {
  const tree = cloneTree(root)
  // 纵拉前拆掉「左右 spacer + 叶子」的宽度种子包装，避免手抖改 ratios 把窄 KPI 挤没
  if (axis === 'y') {
    unwrapSeedWidthWraps(tree, blockId)
  }
  const loc = findLeafParent(tree, blockId)
  if (!loc) return null

  if (axis === 'y') {
    return ensureHeightPair(tree, loc.parent, loc.index, loc.leaf, side)
  }
  return ensureWidthPair(tree, loc.parent, loc.index, loc.leaf, side)
}

/**
 * 若叶子被包在「仅含 spacer + 该叶子」的 row 里，上提到父级，去掉无用的宽度种子层。
 * 可叠多层（先左右再缺侧），直到父级不再是纯种子 row。
 */
function unwrapSeedWidthWraps(tree: FlexContainer, blockId: string): void {
  for (let guard = 0; guard < 6; guard++) {
    const loc = findLeafParent(tree, blockId)
    if (!loc || loc.parent.type !== 'row') return
    if (!isSeedWidthRow(loc.parent)) return
    const outer = findContainerParent(tree, loc.parent.id)
    if (!outer) return
    const wrap = loc.parent
    const leaf = loc.leaf
    leaf.grow = wrap.grow ?? leaf.grow ?? 1
    outer.parent.children[outer.index] = leaf
  }
}

/** row 子项仅为「一个内容叶子 + 若干 spacer」时视为宽度种子包装 */
function isSeedWidthRow(row: FlexContainer): boolean {
  if (row.type !== 'row' || row.gap_pt !== 0) return false
  let leaves = 0
  for (const child of row.children) {
    if (isSpacer(child)) continue
    if (child.type === 'block') {
      leaves += 1
      continue
    }
    return false
  }
  return leaves === 1 && row.children.length >= 2
}

function ensureHeightPair(
  tree: FlexContainer,
  parent: FlexContainer,
  index: number,
  leaf: FlexLeaf,
  side: ResizeSide,
): ResizePair | null {
  if (parent.type === 'column') {
    // 目标侧已有兄弟：用真分隔线。缺侧不要把 spacer 插进带 gap 的父列，
    // 否则 grow=0 仍吃掉 gap，顶/底永远回不到满高。
    if (side === 'after' && index < parent.children.length - 1) {
      return pairInContainer(tree, parent, index, side)
    }
    if (side === 'before' && index > 0) {
      return pairInContainer(tree, parent, index, side)
    }
    return wrapLeafInCell(tree, parent, index, leaf, side, 'column')
  }
  // 父为 row：同行子项共享行高，直接调行的 grow 会连带改变兄弟单元格。
  // 就地把该叶子单独包一层 column，让高度只作用于这一格。
  return wrapLeafInCell(tree, parent, index, leaf, side, 'column')
}

function ensureWidthPair(
  tree: FlexContainer,
  parent: FlexContainer,
  index: number,
  leaf: FlexLeaf,
  side: ResizeSide,
): ResizePair | null {
  if (parent.type === 'row') {
    return pairInContainer(tree, parent, index, side)
  }
  // 通栏列、或先补高度占位后的 [内容|spacer] cell：宽度打到外层 row，
  // 避免再包一层 seed row 导致「上下拖」误改内层宽度。
  const outer = findContainerParent(tree, parent.id)
  if (outer?.parent.type === 'row' && isTrivialWidthColumn(parent)) {
    return pairInContainer(tree, outer.parent, outer.index, side)
  }
  return wrapLeafInCell(tree, parent, index, leaf, side, 'row')
}

/** 单子通栏列，或高度包装 cell（gap=0 且含 spacer） */
function isTrivialWidthColumn(column: FlexContainer): boolean {
  if (column.type !== 'column') return false
  if (column.children.length === 1) return true
  if (column.gap_pt === 0 && column.children.length === 2) {
    return column.children.some((child) => isSpacer(child))
  }
  return false
}

/** 就地把叶子包进一个只含它与占位块的容器，让拉伸只作用于这一格 */
function wrapLeafInCell(
  tree: FlexContainer,
  parent: FlexContainer,
  index: number,
  leaf: FlexLeaf,
  side: ResizeSide,
  type: 'row' | 'column',
): ResizePair | null {
  const sized: FlexLeaf = { ...leaf, grow: type === 'column' ? GROW_MAX : (leaf.grow ?? 1) }
  const spacer = makeSpacer(type === 'column' ? SPACER_SEED_GROW : 1)
  const cell: FlexContainer = {
    type,
    id: newNodeId('cell'),
    gap_pt: 0,
    grow: parent.children[index]?.grow ?? 1,
    children: side === 'before' ? [spacer, sized] : [sized, spacer],
    ratios:
      type === 'row'
        ? side === 'before'
          ? [SPACER_SEED_RATIO, 100 - SPACER_SEED_RATIO]
          : [100 - SPACER_SEED_RATIO, SPACER_SEED_RATIO]
        : null,
  }
  parent.children[index] = cell
  return { tree, containerId: cell.id, index: 0 }
}

/**
 * 在容器内为第 index 项取一条可拖的分隔线：
 * 目标侧已有兄弟就直接用相邻分隔线，否则补一个最小份额占位块。
 */
function pairInContainer(
  tree: FlexContainer,
  container: FlexContainer,
  index: number,
  side: ResizeSide,
): ResizePair | null {
  if (side === 'after' && index < container.children.length - 1) {
    return { tree, containerId: container.id, index }
  }
  if (side === 'before' && index > 0) {
    return { tree, containerId: container.id, index: index - 1 }
  }
  if (!insertSpacerSharing(container, index, side === 'after' ? index + 1 : index)) {
    return null
  }
  return { tree, containerId: container.id, index }
}

/** 在 at 处插入占位块，只扣种子份额，几何几乎不变；拖动后再拉开 */
function insertSpacerSharing(
  container: FlexContainer,
  unitIndex: number,
  at: number,
): boolean {
  const unit = container.children[unitIndex]
  if (!unit) return false

  if (container.type === 'row') {
    const count = container.children.length
    const ratios =
      container.ratios?.length === count
        ? [...container.ratios]
        : Array.from({ length: count }, () => 100 / count)
    const current = ratios[unitIndex] ?? 100 / count
    const take = Math.min(SPACER_SEED_RATIO, Math.max(current / 2, SPACER_SEED_RATIO))
    ratios[unitIndex] = Math.max(current - take, SPACER_SEED_RATIO)
    ratios.splice(at, 0, take)
    container.children.splice(at, 0, makeSpacer(1))
    container.ratios = normalizeRatioSum(ratios)
    return true
  }

  const current = unit.grow ?? 1
  const take = Math.min(SPACER_SEED_GROW, Math.max(current / 2, SPACER_SEED_GROW))
  unit.grow = Math.max(current - take, SPACER_SEED_GROW)
  container.children.splice(at, 0, makeSpacer(take))
  return true
}

function normalizeRatioSum(ratios: number[]): number[] {
  const total = ratios.reduce((a, b) => a + b, 0)
  if (total <= 0) return ratios.map(() => 100 / ratios.length)
  return ratios.map((r) => (r / total) * 100)
}
