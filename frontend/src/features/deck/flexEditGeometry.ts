import type { CSSProperties } from 'react'
import type { ResizeSide } from '@/features/deck/flexTree'

export type RectLike = { x: number; y: number; w: number; h: number }

export const pct = (value: number) => `${value * 100}%`

/**
 * 对角线判定：次轴 / 主轴 ≥ 该值才视为双轴，否则锁主轴。
 * 偏严，避免「上下拖时手抖左右」改宽度。
 */
const AXIS_DIAGONAL_MIN = 0.7
/** 角点激活：横向位移未达此像素前不补宽度拉伸对，避免纯纵向拖留下宽度包装 */
export const AXIS_X_GATE_PX = 12
/** 窄于此时隐藏角点，只留边手柄，避免三列 KPI 误触双轴 */
export const NARROW_BLOCK_HIDE_CORNER = 0.32
/** 缩放 / 插入：小于该像素位移视为点击，不改树或不落拖放 */
export const DRAG_ACTIVATE_PX = 3

/**
 * 边手柄相对块尺寸让出四角。
 * 不用整页绝对 inset，否则三列 KPI 等窄块上下边命中会被吃光。
 */
export function edgeCornerInset(rect: RectLike): { x: number; y: number } {
  const minEdgeW = Math.max(rect.w * 0.4, Math.min(0.02, rect.w))
  const minEdgeH = Math.max(rect.h * 0.4, Math.min(0.02, rect.h))
  const maxInsetX = Math.max(0, (rect.w - minEdgeW) / 2)
  const maxInsetY = Math.max(0, (rect.h - minEdgeH) / 2)
  return {
    x: Math.min(Math.min(0.02, rect.w * 0.18), maxInsetX),
    y: Math.min(Math.min(0.02, rect.h * 0.18), maxInsetY),
  }
}

/** 排序柄放在块外，避免压住窄 KPI 左侧数字 */
export function gripOffsetStyle(rect: RectLike): CSSProperties {
  const gripPx = 22
  // 贴左边时改放到上方，防止柄本身被画布裁掉
  if (rect.x < 0.04) {
    return {
      left: `calc(${rect.x * 100}% + 3px)`,
      top: `calc(${rect.y * 100}% - ${gripPx}px)`,
    }
  }
  return {
    left: `calc(${rect.x * 100}% - ${gripPx}px)`,
    top: `calc(${rect.y * 100}% + 3px)`,
  }
}

/** 四条边手柄：左/上取相邻的前一条分隔线，右/下取后一条 */
export const EDGE_HANDLES: {
  key: string
  axis: 'x' | 'y'
  side: ResizeSide
  title: string
  className: string
  barClassName: string
  style: (rect: RectLike) => CSSProperties
}[] = [
  {
    key: 'top',
    axis: 'y',
    side: 'before',
    title: '拖动调整高度',
    className: 'h-3 -translate-y-1/2 cursor-row-resize',
    barClassName: 'h-1 w-9 rounded-full bg-accent/75 shadow-sm',
    style: (rect) => {
      const inset = edgeCornerInset(rect)
      return {
        left: pct(rect.x + inset.x),
        top: pct(rect.y),
        width: pct(Math.max(rect.w - 2 * inset.x, 0)),
      }
    },
  },
  {
    key: 'bottom',
    axis: 'y',
    side: 'after',
    title: '拖动调整高度',
    className: 'h-3 -translate-y-1/2 cursor-row-resize',
    barClassName: 'h-1 w-9 rounded-full bg-accent/75 shadow-sm',
    style: (rect) => {
      const inset = edgeCornerInset(rect)
      return {
        left: pct(rect.x + inset.x),
        top: pct(rect.y + rect.h),
        width: pct(Math.max(rect.w - 2 * inset.x, 0)),
      }
    },
  },
  {
    key: 'left',
    axis: 'x',
    side: 'before',
    title: '拖动调整宽度',
    className: 'w-3 -translate-x-1/2 cursor-col-resize',
    barClassName: 'h-9 w-1 rounded-full bg-accent/75 shadow-sm',
    style: (rect) => {
      const inset = edgeCornerInset(rect)
      return {
        left: pct(rect.x),
        top: pct(rect.y + inset.y),
        height: pct(Math.max(rect.h - 2 * inset.y, 0)),
      }
    },
  },
  {
    key: 'right',
    axis: 'x',
    side: 'after',
    title: '拖动调整宽度',
    className: 'w-3 -translate-x-1/2 cursor-col-resize',
    barClassName: 'h-9 w-1 rounded-full bg-accent/75 shadow-sm',
    style: (rect) => {
      const inset = edgeCornerInset(rect)
      return {
        left: pct(rect.x + rect.w),
        top: pct(rect.y + inset.y),
        height: pct(Math.max(rect.h - 2 * inset.y, 0)),
      }
    },
  },
]

/** 四角手柄：同时开横纵两条分隔线 */
export const CORNER_HANDLES: {
  key: string
  sideX: ResizeSide
  sideY: ResizeSide
  className: string
  style: (rect: RectLike) => CSSProperties
}[] = [
  {
    key: 'nw',
    sideX: 'before',
    sideY: 'before',
    className: 'cursor-nwse-resize',
    style: (rect) => ({ left: pct(rect.x), top: pct(rect.y) }),
  },
  {
    key: 'ne',
    sideX: 'after',
    sideY: 'before',
    className: 'cursor-nesw-resize',
    style: (rect) => ({ left: pct(rect.x + rect.w), top: pct(rect.y) }),
  },
  {
    key: 'sw',
    sideX: 'before',
    sideY: 'after',
    className: 'cursor-nesw-resize',
    style: (rect) => ({ left: pct(rect.x), top: pct(rect.y + rect.h) }),
  },
  {
    key: 'se',
    sideX: 'after',
    sideY: 'after',
    className: 'cursor-nwse-resize',
    style: (rect) => ({ left: pct(rect.x + rect.w), top: pct(rect.y + rect.h) }),
  },
]

export function movedPastThreshold(
  startClientX: number,
  startClientY: number,
  clientX: number,
  clientY: number,
): boolean {
  const dx = clientX - startClientX
  const dy = clientY - startClientY
  return dx * dx + dy * dy >= DRAG_ACTIVATE_PX * DRAG_ACTIVATE_PX
}

/** 按首段位移锁定缩放主轴；明显对角线才双轴 */
export function resolveAxisLock(dx: number, dy: number): 'x' | 'y' | 'both' {
  const adx = Math.abs(dx)
  const ady = Math.abs(dy)
  if (adx < 1e-6 && ady < 1e-6) return 'y'
  const dominant = Math.max(adx, ady)
  const minor = Math.min(adx, ady)
  if (minor / dominant >= AXIS_DIAGONAL_MIN) return 'both'
  return ady >= adx ? 'y' : 'x'
}

/**
 * 角点专用：横向未过像素门槛强制纯 Y，避免上下拉时手抖改宽。
 */
export function resolveCornerAxisLock(dx: number, dy: number): 'x' | 'y' | 'both' {
  if (Math.abs(dx) < AXIS_X_GATE_PX) return 'y'
  return resolveAxisLock(dx, dy)
}
