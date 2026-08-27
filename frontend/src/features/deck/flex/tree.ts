import type { FlexContainer, FlexLeaf, FlexNode, GroupPreset } from '@/render/flexLayout'

import { GROW_MAX, GROW_MIN, GROW_SOFT_MIN, RATIO_MIN } from './constants'

export function isLeaf(node: FlexNode): node is FlexLeaf {
  return node.type === 'block'
}

export function isContainer(node: FlexNode): node is FlexContainer {
  return node.type === 'row' || node.type === 'column'
}

export function cloneTree(tree: FlexContainer): FlexContainer {
  return structuredClone(tree)
}

export function newNodeId(prefix: string): string {
  return `${prefix}-${crypto.randomUUID().replace(/-/g, '').slice(0, 10)}`
}

export function findLeafParent(
  root: FlexContainer,
  blockId: string,
): { parent: FlexContainer; index: number; leaf: FlexLeaf } | null {
  for (let index = 0; index < root.children.length; index++) {
    const child = root.children[index]!
    if (isLeaf(child) && child.block_id === blockId) {
      return { parent: root, index, leaf: child }
    }
    if (isContainer(child)) {
      const found = findLeafParent(child, blockId)
      if (found) return found
    }
  }
  return null
}

/** 侧栏插入：选中块之后；无选中则根容器末尾 */
export function resolveInsertAnchor(
  root: FlexContainer,
  selectedBlockId: string | null,
): { parentId: string; index: number } {
  if (selectedBlockId) {
    const found = findLeafParent(root, selectedBlockId)
    if (found) {
      return { parentId: found.parent.id, index: found.index + 1 }
    }
  }
  return { parentId: root.id, index: root.children.length }
}

export function findContainerById(
  root: FlexContainer,
  containerId: string,
): FlexContainer | null {
  if (root.id === containerId) return root
  for (const child of root.children) {
    if (isContainer(child)) {
      const found = findContainerById(child, containerId)
      if (found) return found
    }
  }
  return null
}

export function iterLeaves(node: FlexNode): FlexLeaf[] {
  if (isLeaf(node)) return [node]
  return node.children.flatMap(iterLeaves)
}

export function isSpacer(node: FlexNode): boolean {
  return isContainer(node) && node.id.startsWith('spacer-')
}

export function makeSpacer(grow = 1): FlexContainer {
  return {
    type: 'column',
    id: newNodeId('spacer'),
    children: [],
    gap_pt: 0,
    grow,
  }
}

function rowRatios(parent: FlexContainer): number[] {
  const n = parent.children.length
  if (n <= 0) return []
  if (parent.ratios != null && parent.ratios.length === n) return [...parent.ratios]
  return Array.from({ length: n }, () => 100 / n)
}

function pickSpacerIndex(parent: FlexContainer, preferNear: number): number {
  let best = -1
  let bestGrow = -1
  for (let i = 0; i < parent.children.length; i++) {
    const child = parent.children[i]!
    if (!isSpacer(child)) continue
    const grow = child.grow ?? 1
    const near = i === preferNear || i === preferNear - 1
    if (near) return i
    if (grow > bestGrow) {
      bestGrow = grow
      best = i
    }
  }
  return best
}

/**
 * 将 block 移到目标容器的 index。
 * 同父：只换序，不改 grow/ratios。
 * 跨父：原位留等权 spacer，目标优先吃掉 spacer，避免内容块因换位变形。
 */
export function moveLeaf(
  root: FlexContainer,
  blockId: string,
  targetParentId: string,
  index: number,
): FlexContainer | null {
  const origin = findLeafParent(root, blockId)
  if (!origin) return null

  if (origin.parent.id === targetParentId) {
    return moveLeafSameParent(root, blockId, index)
  }
  return moveLeafAcrossParents(root, blockId, targetParentId, index)
}

function moveLeafSameParent(
  root: FlexContainer,
  blockId: string,
  index: number,
): FlexContainer | null {
  const tree = cloneTree(root)
  const found = findLeafParent(tree, blockId)
  if (!found) return null
  const parent = found.parent
  let insertAt = index
  if (found.index < index) insertAt -= 1
  insertAt = Math.max(0, Math.min(insertAt, parent.children.length - 1))
  if (insertAt === found.index) return null

  const ratios = parent.type === 'row' ? rowRatios(parent) : null
  const [leaf] = parent.children.splice(found.index, 1) as [FlexLeaf]
  const takenRatio = ratios ? ratios.splice(found.index, 1)[0]! : null
  parent.children.splice(insertAt, 0, leaf)
  if (ratios && takenRatio != null) {
    ratios.splice(insertAt, 0, takenRatio)
    parent.ratios = ratios
  }
  return tree
}

function moveLeafAcrossParents(
  root: FlexContainer,
  blockId: string,
  targetParentId: string,
  index: number,
): FlexContainer | null {
  const tree = cloneTree(root)
  const src = findLeafParent(tree, blockId)
  if (!src) return null
  const target = findContainerById(tree, targetParentId)
  if (!target) return null

  const leafGrow = src.leaf.grow ?? 1
  const srcParent = src.parent
  const srcIndex = src.index

  // 原位：叶子换成等权 spacer，保留 grow / ratio，其它兄弟尺寸不变
  if (srcParent.type === 'row') {
    const ratios = rowRatios(srcParent)
    const [leaf] = srcParent.children.splice(srcIndex, 1) as [FlexLeaf]
    const leafRatio = ratios.splice(srcIndex, 1)[0] ?? 100 / Math.max(ratios.length + 1, 1)
    const spacer = makeSpacer(leafGrow)
    srcParent.children.splice(srcIndex, 0, spacer)
    ratios.splice(srcIndex, 0, leafRatio)
    srcParent.ratios = ratios
    return placeLeafAtTarget(tree, target, index, leaf, leafGrow, leafRatio)
  }

  const [leaf] = srcParent.children.splice(srcIndex, 1) as [FlexLeaf]
  srcParent.children.splice(srcIndex, 0, makeSpacer(leafGrow))
  return placeLeafAtTarget(tree, target, index, leaf, leafGrow, null)
}

function renormalizeRatios(ratios: number[]): number[] {
  const total = ratios.reduce((sum, value) => sum + value, 0) || 1
  return ratios.map((value) => (value / total) * 100)
}

function placeLeafAtTarget(
  tree: FlexContainer,
  target: FlexContainer,
  index: number,
  leaf: FlexLeaf,
  leafGrow: number,
  leafRatio: number | null,
): FlexContainer {
  leaf.grow = leafGrow
  const insertAt = Math.max(0, Math.min(index, target.children.length))
  const spacerIndex = pickSpacerIndex(target, insertAt)

  if (spacerIndex >= 0) {
    const spacer = target.children[spacerIndex] as FlexContainer
    const spacerGrow = spacer.grow ?? 1

    // spacer 权重大致够：直接替换，内容兄弟权重不动
    if (spacerGrow <= leafGrow + 1e-6) {
      if (target.type === 'row') {
        const ratios = rowRatios(target)
        ratios[spacerIndex] = leafRatio ?? ratios[spacerIndex]!
        target.ratios = renormalizeRatios(ratios)
      }
      target.children.splice(spacerIndex, 1, leaf)
      return tree
    }

    // spacer 更大：扣减后在落点插入叶子
    spacer.grow = Math.max(GROW_MIN, spacerGrow - leafGrow)
    if (target.type === 'row') {
      const ratios = rowRatios(target)
      const spacerRatio = ratios[spacerIndex]!
      const take =
        leafRatio != null ? Math.min(leafRatio, spacerRatio * 0.9) : spacerRatio / 2
      ratios[spacerIndex] = Math.max(RATIO_MIN, spacerRatio - take)
      let place = Math.max(0, Math.min(insertAt, target.children.length))
      target.children.splice(place, 0, leaf)
      ratios.splice(place, 0, Math.max(RATIO_MIN, take))
      target.ratios = renormalizeRatios(ratios)
      return tree
    }
    const place = Math.max(0, Math.min(insertAt, target.children.length))
    target.children.splice(place, 0, leaf)
    return tree
  }

  // 无 spacer：保留原 grow 插入，不对邻居对半拆分
  if (target.type === 'row') {
    const ratios = rowRatios(target)
    const share =
      leafRatio != null && leafRatio > 0
        ? leafRatio
        : 100 / Math.max(target.children.length + 1, 1)
    target.children.splice(insertAt, 0, leaf)
    ratios.splice(insertAt, 0, share)
    target.ratios = renormalizeRatios(ratios)
    return tree
  }
  target.children.splice(insertAt, 0, leaf)
  return tree
}

/** 把若干同级叶子包进 row → 每列一个 column → 叶子 */
export function wrapBlockIdsAsColumns(
  root: FlexContainer,
  blockIds: string[],
): FlexContainer | null {
  if (blockIds.length < 2) return null
  const tree = cloneTree(root)
  const locations = blockIds.map((id) => findLeafParent(tree, id))
  if (locations.some((loc) => loc == null)) return null
  const parent = locations[0]!.parent
  if (locations.some((loc) => loc!.parent.id !== parent.id)) return null

  const indices = locations.map((loc) => loc!.index).sort((a, b) => a - b)
  // 必须连续同级
  for (let i = 1; i < indices.length; i++) {
    if (indices[i] !== indices[i - 1]! + 1) return null
  }

  const leaves = indices.map((i) => parent.children[i] as FlexLeaf)
  const start = indices[0]!
  parent.children.splice(start, leaves.length)

  const columns: FlexContainer[] = leaves.map((leaf) => ({
    type: 'column',
    id: newNodeId('col'),
    children: [leaf],
    gap_pt: 16,
    grow: 1,
  }))

  const row: FlexContainer = {
    type: 'row',
    id: newNodeId('row'),
    children: columns,
    gap_pt: 16,
    ratios: Array.from({ length: columns.length }, () => 100 / columns.length),
    grow: 1,
  }
  parent.children.splice(start, 0, row)
  return tree
}

export function updateRowRatios(
  root: FlexContainer,
  rowId: string,
  ratios: number[],
): FlexContainer | null {
  const tree = cloneTree(root)
  const row = findContainerById(tree, rowId)
  if (!row || row.type !== 'row') return null
  row.ratios = ratios
  return tree
}

export function updateChildGrows(
  root: FlexContainer,
  containerId: string,
  grows: number[],
): FlexContainer | null {
  const tree = cloneTree(root)
  const container = findContainerById(tree, containerId)
  if (!container || container.type !== 'column') return null
  if (grows.length !== container.children.length) return null
  for (let i = 0; i < container.children.length; i++) {
    const child = container.children[i]!
    // spacer → 0；内容侧用软下限，拉伸时才能从兄弟多偷一点高度
    const floor = isSpacer(child) ? 0 : GROW_SOFT_MIN
    child.grow = Math.min(GROW_MAX, Math.max(floor, grows[i]!))
  }
  return tree
}

/** preset=null 表示清除容器预设皮肤 */
export function setContainerPreset(
  root: FlexContainer,
  containerId: string,
  preset: GroupPreset | null,
): FlexContainer | null {
  const tree = cloneTree(root)
  const container = findContainerById(tree, containerId)
  if (!container) return null
  container.preset = preset
  return tree
}

export function findContainerParent(
  root: FlexContainer,
  containerId: string,
): { parent: FlexContainer; index: number } | null {
  const walk = (
    node: FlexContainer,
  ): { parent: FlexContainer; index: number } | null => {
    for (let i = 0; i < node.children.length; i++) {
      const child = node.children[i]!
      if (isContainer(child)) {
        if (child.id === containerId) return { parent: node, index: i }
        const found = walk(child)
        if (found) return found
      }
    }
    return null
  }
  return walk(root)
}
