import type { FlexNode } from '@/render/flexLayout'

import type { RectLike } from './constants'
import { isContainer, isLeaf, iterLeaves } from './tree'

export function unionRects(rects: RectLike[]): RectLike | null {
  if (rects.length === 0) return null
  let x0 = Infinity
  let y0 = Infinity
  let x1 = -Infinity
  let y1 = -Infinity
  for (const r of rects) {
    x0 = Math.min(x0, r.x)
    y0 = Math.min(y0, r.y)
    x1 = Math.max(x1, r.x + r.w)
    y1 = Math.max(y1, r.y + r.h)
  }
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 }
}

export function nodeBounds(
  node: FlexNode,
  placements: Map<string, RectLike>,
  nodeAreas?: Map<string, RectLike>,
): RectLike | null {
  if (isContainer(node) && nodeAreas?.has(node.id)) {
    return nodeAreas.get(node.id) ?? null
  }
  if (isLeaf(node)) {
    return placements.get(node.block_id) ?? nodeAreas?.get(node.id) ?? null
  }
  const rects = iterLeaves(node)
    .map((leaf) => placements.get(leaf.block_id))
    .filter((r): r is RectLike => r != null)
  return unionRects(rects) ?? (nodeAreas?.get(node.id) ?? null)
}
