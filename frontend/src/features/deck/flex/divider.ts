import { solveNodeAreas, type FlexContainer } from '@/render/flexLayout'

import type { RectLike } from './constants'
import { nodeBounds } from './geometry'
import { isContainer } from './tree'

export type RowDivider = {
  rowId: string
  leftIndex: number
  /** 归一化坐标 */
  x: number
  y: number
  h: number
}

export type ColumnDivider = {
  columnId: string
  topIndex: number
  x: number
  y: number
  w: number
}

export function collectRowDividers(
  root: FlexContainer,
  placements: Map<string, RectLike>,
): RowDivider[] {
  const result: RowDivider[] = []
  const nodeAreas = solveNodeAreas(root)

  const walk = (node: FlexContainer) => {
    if (node.type === 'row' && node.children.length >= 2) {
      const bounds = node.children.map((child) =>
        nodeBounds(child, placements, nodeAreas),
      )
      for (let i = 0; i < node.children.length - 1; i++) {
        const left = bounds[i]
        const right = bounds[i + 1]
        if (!left || !right) continue
        const x = (left.x + left.w + right.x) / 2
        const y = Math.min(left.y, right.y)
        const h = Math.max(left.y + left.h, right.y + right.h) - y
        result.push({ rowId: node.id, leftIndex: i, x, y, h })
      }
    }
    for (const child of node.children) {
      if (isContainer(child)) walk(child)
    }
  }

  walk(root)
  return result
}

export function collectColumnDividers(
  root: FlexContainer,
  placements: Map<string, RectLike>,
): ColumnDivider[] {
  const result: ColumnDivider[] = []
  const nodeAreas = solveNodeAreas(root)

  const walk = (node: FlexContainer) => {
    if (node.type === 'column' && node.children.length >= 2) {
      const bounds = node.children.map((child) =>
        nodeBounds(child, placements, nodeAreas),
      )
      for (let i = 0; i < node.children.length - 1; i++) {
        const top = bounds[i]
        const bottom = bounds[i + 1]
        if (!top || !bottom) continue
        const y = (top.y + top.h + bottom.y) / 2
        const x = Math.min(top.x, bottom.x)
        const w = Math.max(top.x + top.w, bottom.x + bottom.w) - x
        result.push({ columnId: node.id, topIndex: i, x, y, w })
      }
    }
    for (const child of node.children) {
      if (isContainer(child)) walk(child)
    }
  }

  walk(root)
  return result
}
