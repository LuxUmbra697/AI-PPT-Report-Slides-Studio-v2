import { GROW_MAX, GROW_MIN, isSpacer } from '@/features/deck/flexTree'
import type { FlexContainer, FlexNode } from '@/render/flexLayout'

/**
 * grow 归一化：与 backend/app/domain/flex_normalize.py 的 grow 分支逐行对齐。
 *
 * 编辑链路的后端固定用 clamp_title_grow=False，所以这里不钳制标题；
 * ratios 由 flexTree 的 snapRatios 对齐，深度/行子数上限在编辑路径不触发。
 * 两端不一致时，拖拽结果会在保存后被服务端改写，表现为松手后元素再跳一次。
 */
export function normalizeGrows(tree: FlexContainer): FlexContainer {
  return normalizeContainer(tree)
}

function normalizeContainer(node: FlexContainer): FlexContainer {
  const children = node.children.map(normalizeChild).map(clampNodeGrow)
  return {
    ...node,
    children: normalizeSiblingGrows(children),
    grow: isSpacer(node) ? clampSpacerGrow(growOf(node)) : clampGrow(growOf(node)),
  }
}

function normalizeChild(node: FlexNode): FlexNode {
  return node.type === 'block' ? node : normalizeContainer(node)
}

function clampNodeGrow(node: FlexNode): FlexNode {
  return withGrow(node, isSpacer(node) ? clampSpacerGrow(growOf(node)) : clampGrow(growOf(node)))
}

/** 占位块允许 grow=0，才能把顶/底边拖回满高原位并在保存后保持 */
function clampSpacerGrow(grow: number): number {
  return Math.max(0, Math.min(GROW_MAX, grow))
}

function clampGrow(grow: number): number {
  return Math.max(GROW_MIN, Math.min(GROW_MAX, grow))
}

function growOf(node: FlexNode): number {
  return node.grow ?? 1
}

function withGrow(node: FlexNode, grow: number): FlexNode {
  return node.type === 'block' ? { ...node, grow } : { ...node, grow }
}

/** spacer 固定不参与重平衡；其余按权重分剩余额度，触边后锁定再分配，保证幂等 */
function normalizeSiblingGrows(children: FlexNode[]): FlexNode[] {
  if (children.length === 0) return children
  const n = children.length
  const grows: number[] = []
  const locked: boolean[] = []
  for (const child of children) {
    if (isSpacer(child)) {
      grows.push(clampSpacerGrow(growOf(child)))
      locked.push(true)
    } else {
      grows.push(clampGrow(growOf(child)))
      locked.push(false)
    }
  }

  let free = grows.map((_, index) => index).filter((index) => !locked[index])
  const hasSpacer = children.some((child) => isSpacer(child))

  for (let round = 0; round < n + 2; round++) {
    if (free.length === 0) break
    const isFree = new Set(free)
    let lockedSum = 0
    for (let index = 0; index < n; index++) {
      if (!isFree.has(index)) lockedSum += grows[index]!
    }
    let weightSum = 0
    for (const index of free) weightSum += grows[index]!
    // 有 spacer 时保留内容块绝对权重，避免占位把邻居重标扁
    const remaining = hasSpacer ? weightSum : n - lockedSum
    if (remaining <= 0) {
      for (const index of free) grows[index] = GROW_MIN
      break
    }
    if (weightSum <= 0) {
      const equal = remaining / free.length
      for (const index of free) grows[index] = equal
    } else {
      for (const index of free) grows[index] = (grows[index]! * remaining) / weightSum
    }

    const nextFree: number[] = []
    for (const index of free) {
      const clamped = clampGrow(grows[index]!)
      if (clamped !== grows[index]) grows[index] = clamped
      else nextFree.push(index)
    }
    if (nextFree.length === free.length) break
    free = nextFree
  }

  return children.map((child, index) => withGrow(child, grows[index]!))
}
