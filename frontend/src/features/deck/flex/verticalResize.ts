import { solveNodeAreas, type FlexContainer } from '@/render/flexLayout'

import { GROW_SOFT_MIN } from './constants'
import { growsFromDividerDrag } from './ratio'
import {
  findContainerById,
  findContainerParent,
  isSpacer,
  updateChildGrows,
} from './tree'

/** 内容侧分隔线保底份额；spacer 侧用 0 */
const CONTENT_SIDE_MIN = GROW_SOFT_MIN

/**
 * 从 startId 向上找最近的、可偷兄弟的 column 祖先。
 * expandDown：优先能偷下方（footer），否则偷上方；expandUp 相反。
 */
function findBubbleColumn(
  root: FlexContainer,
  startId: string,
  expandDown: boolean,
): { columnId: string; branchIndex: number } | null {
  let loc = findContainerParent(root, startId)
  while (loc) {
    if (loc.parent.type === 'column' && loc.parent.children.length >= 2) {
      const canStealBelow = loc.index < loc.parent.children.length - 1
      const canStealAbove = loc.index > 0
      if (expandDown ? canStealBelow || canStealAbove : canStealAbove || canStealBelow) {
        return { columnId: loc.parent.id, branchIndex: loc.index }
      }
    }
    loc = findContainerParent(root, loc.parent.id)
  }
  return null
}

/** 触底后沿祖先 column 逐级偷高，直到位移耗尽或无更多兄弟可偷 */
function cascadeBubbleGrow(args: {
  tree: FlexContainer
  startId: string
  remainingY: number
  expandDown: boolean
  colH: number
}): FlexContainer | null {
  let tree = args.tree
  let remainingY = args.remainingY
  let cursorId = args.startId
  for (let guard = 0; guard < 8 && Math.abs(remainingY) > 1e-5; guard++) {
    const bubble = findBubbleColumn(tree, cursorId, args.expandDown)
    if (!bubble) break
    const beforeH = branchNormH(tree, bubble.columnId, bubble.branchIndex)
    const next = applyBubbleGrow({
      tree,
      columnId: bubble.columnId,
      branchIndex: bubble.branchIndex,
      deltaY: remainingY,
      expandDown: args.expandDown,
      colH: args.colH,
    })
    if (!next) break
    const afterH = branchNormH(next, bubble.columnId, bubble.branchIndex)
    const gained = afterH - beforeH
    tree = next
    if (Math.abs(gained) <= 1e-6) break
    // 下扩 gained>0；上扩 branch 变高时 gained 亦 >0，remainingY 为负则加上 gained 向 0 收敛
    remainingY = args.expandDown ? remainingY - gained : remainingY + gained
    cursorId = bubble.columnId
  }
  return tree
}

function branchNormH(
  tree: FlexContainer,
  columnId: string,
  branchIndex: number,
): number {
  const column = findContainerById(tree, columnId)
  const area = solveNodeAreas(tree).get(columnId)
  if (!column || !area) return 0
  const grows = column.children.map((child) => child.grow ?? 1)
  const total = grows.reduce((a, b) => a + b, 0)
  if (total <= 0) return 0
  return ((grows[branchIndex] ?? 0) / total) * area.h
}

function applyBubbleGrow(args: {
  tree: FlexContainer
  columnId: string
  branchIndex: number
  /** 指针相对 origin 的位移（归一化）；下为正 */
  deltaY: number
  expandDown: boolean
  colH: number
}): FlexContainer | null {
  const { tree, columnId, branchIndex, deltaY, expandDown, colH } = args
  const column = findContainerById(tree, columnId)
  if (!column || column.type !== 'column') return null
  const grows = column.children.map((child) => child.grow ?? 1)
  const parentArea = solveNodeAreas(tree).get(columnId)
  const parentH = parentArea?.h ?? colH

  // 下扩：先偷下方兄弟（增大 branch、减小 below），否则偷上方
  // 上扩：先偷上方，否则偷下方
  let topIndex: number
  let invert: boolean
  if (expandDown) {
    if (branchIndex < grows.length - 1) {
      topIndex = branchIndex
      invert = false // 指针下移 → t 增大 → 上方(branch)变大
    } else if (branchIndex > 0) {
      topIndex = branchIndex - 1
      invert = true // 指针下移 → t 减小 → 下方(branch)变大
    } else {
      return null
    }
  } else if (branchIndex > 0) {
    topIndex = branchIndex - 1
    invert = false // 指针上移 deltaY<0 → t 减小 → 上方变小、branch 变大… 需 invert
    // 上扩：指针上移应增大下方 branch。topIndex=branch-1，减小 t → 上方变小、下方变大。
    // parentT = startT + deltaY/H；deltaY<0 → t 降 → 下方变大。invert=false ✓
  } else if (branchIndex < grows.length - 1) {
    topIndex = branchIndex
    invert = true
  } else {
    return null
  }

  const startParentT = growStartT(grows, topIndex)
  const parentT = invert
    ? startParentT - deltaY / Math.max(parentH, 1e-9)
    : startParentT + deltaY / Math.max(parentH, 1e-9)
  return updateChildGrows(
    tree,
    columnId,
    growsFromDividerDrag({
      grows,
      topIndex,
      t: parentT,
      minTop: CONTENT_SIDE_MIN,
      minBottom: CONTENT_SIDE_MIN,
    }),
  )
}

/**
 * 纵向边拖：先改 column 内相邻 grow；
 * 邻侧已触底（spacer=0 或内容软下限）仍继续外扩时，沿祖先 column 偷兄弟高度。
 */
export function applyVerticalResizeDrag(args: {
  root: FlexContainer
  columnId: string
  topIndex: number
  colH: number
  startT: number
  originY: number
  pointerY: number
}): FlexContainer | null {
  const { root, columnId, topIndex, colH, startT, originY, pointerY } = args
  const column = findContainerById(root, columnId)
  if (!column || column.type !== 'column') return null
  const top = column.children[topIndex]
  const bottom = column.children[topIndex + 1]
  if (!top || !bottom) return null

  const minTop = isSpacer(top) ? 0 : CONTENT_SIDE_MIN
  const minBottom = isSpacer(bottom) ? 0 : CONTENT_SIDE_MIN
  const t = startT + (pointerY - originY) / Math.max(colH, 1e-9)
  const grows = column.children.map((child) => child.grow ?? 1)
  const maxT = 1 - minBottom
  const minT = minTop

  // 底边外扩超过本对可给额度 → 邻侧触底后沿祖先逐级偷高
  if (t > maxT) {
    let tree = updateChildGrows(
      root,
      columnId,
      growsFromDividerDrag({
        grows,
        topIndex,
        t: maxT,
        minTop,
        minBottom,
      }),
    )
    if (!tree) return null
    return (
      cascadeBubbleGrow({
        tree,
        startId: columnId,
        remainingY: (t - maxT) * colH,
        expandDown: true,
        colH,
      }) ?? tree
    )
  }

  // 顶边外扩超过本对可给额度
  if (t < minT) {
    let tree = updateChildGrows(
      root,
      columnId,
      growsFromDividerDrag({
        grows,
        topIndex,
        t: minT,
        minTop,
        minBottom,
      }),
    )
    if (!tree) return null
    return (
      cascadeBubbleGrow({
        tree,
        startId: columnId,
        remainingY: (t - minT) * colH,
        expandDown: false,
        colH,
      }) ?? tree
    )
  }

  return updateChildGrows(
    root,
    columnId,
    growsFromDividerDrag({
      grows,
      topIndex,
      t,
      minTop,
      minBottom,
    }),
  )
}

function growStartT(grows: number[], topIndex: number): number {
  const total = grows.reduce((a, b) => a + b, 0)
  if (total <= 0) return 0.5
  let prefix = 0
  for (let i = 0; i <= topIndex; i++) prefix += grows[i] ?? 0
  return prefix / total
}
