export const RATIO_SNAP_TOKENS = [33, 38, 50, 62, 67] as const

/**
 * 与 backend/app/domain/flex_normalize.py 的同名常量保持一致。
 * 不一致会导致拖拽结果在保存后被服务端改写。
 */
export const RATIO_SNAP_TOLERANCE = 2.5
export const GROW_MIN = 0.25
/** 编辑态拉伸允许的内容侧下限（相对/绝对值）；过小会被后端 normalize 抬回 GROW_MIN */
export const GROW_SOFT_MIN = 0.05
export const GROW_MAX = 4
export const OFFSET_LIMIT_PT = 960

/** 缺侧补占位时 spacer 的初始占比：接近 0，避免一点击就缩一截；拖拽时占位侧可收到 0，才能拉回原位 */
export const SPACER_SEED_RATIO = 0.01
/** 缺侧补占位时 spacer 的初始 grow */
export const SPACER_SEED_GROW = 0.001

/** row 子项最小占比（百分比） */
export const RATIO_MIN = 5

/** 最近插槽吸附：超过该归一化距离则放弃（约 25% 画布对角线） */
export const NEAREST_SLOT_MAX_DIST = 0.25

export type FlexBlockType =
  | 'text'
  | 'bullets'
  | 'image'
  | 'chart'
  | 'table'
  | 'kpi'
  | 'cards'
  | 'callout'

export type RectLike = { x: number; y: number; w: number; h: number }
