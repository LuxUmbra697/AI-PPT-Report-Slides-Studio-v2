/**
 * flex 树操作的统一入口；实现按职责分布在 `./flex/` 下。
 */

export {
  GROW_MAX,
  GROW_MIN,
  SPACER_SEED_RATIO,
  type FlexBlockType,
} from './flex/constants'

export {
  findContainerById,
  findLeafParent,
  isSpacer,
  iterLeaves,
  moveLeaf,
  resolveInsertAnchor,
  setContainerPreset,
  updateChildGrows,
  updateRowRatios,
  wrapBlockIdsAsColumns,
} from './flex/tree'

export {
  growsFromDividerDrag,
  ratiosFromDividerDrag,
  snapRatios,
} from './flex/ratio'

export {
  collectColumnDividers,
  collectRowDividers,
  type ColumnDivider,
  type RowDivider,
} from './flex/divider'

export {
  ensureResizePair,
  type ResizePair,
  type ResizeSide,
} from './flex/resizePair'

export { leafOffset, setLeafOffset } from './flex/offset'

export { applyVerticalResizeDrag } from './flex/verticalResize'

export {
  resolveDropTarget,
  type DropTarget,
} from './flex/dropTarget'
