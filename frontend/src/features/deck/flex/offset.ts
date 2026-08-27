import type { FlexContainer } from '@/render/flexLayout'

import { OFFSET_LIMIT_PT } from './constants'
import { cloneTree, findLeafParent, isLeaf, iterLeaves } from './tree'

export function leafOffset(root: FlexContainer, blockId: string): { x: number; y: number } {
  for (const leaf of iterLeaves(root)) {
    if (leaf.block_id === blockId) {
      return { x: leaf.offset_x_pt ?? 0, y: leaf.offset_y_pt ?? 0 }
    }
  }
  return { x: 0, y: 0 }
}

/**
 * 设置叶子的像素级偏移（绝对值，pt）。
 * 只挪位置不改尺寸，越界由 solver 钳制。
 */
export function setLeafOffset(
  root: FlexContainer,
  blockId: string,
  xPt: number,
  yPt: number,
): FlexContainer | null {
  const tree = cloneTree(root)
  const loc = findLeafParent(tree, blockId)
  if (!loc) return null
  const leaf = loc.parent.children[loc.index]
  if (!leaf || !isLeaf(leaf)) return null
  leaf.offset_x_pt = clampOffset(xPt)
  leaf.offset_y_pt = clampOffset(yPt)
  return tree
}

function clampOffset(value: number): number {
  const rounded = Math.round(value * 100) / 100
  return Math.min(OFFSET_LIMIT_PT, Math.max(-OFFSET_LIMIT_PT, rounded))
}
