import {
  GROW_SOFT_MIN,
  RATIO_SNAP_TOLERANCE,
  RATIO_SNAP_TOKENS,
} from './constants'

/**
 * 双列在靠近 33/38/50/62/67 时吸附，否则保留精确比例；多列仅归一化到 100。
 * 无条件吸附会让拖动只有几个离散档位，手感上就是跳。
 */
export function snapRatios(ratios: number[]): number[] {
  const n = ratios.length
  if (n <= 0) return ratios
  if (n === 2) {
    const total = ratios[0]! + ratios[1]!
    if (total <= 0) return [50, 50]
    const pct = sumsTo100(total) ? ratios[0]! : (ratios[0]! / total) * 100
    const pairs = RATIO_SNAP_TOKENS.flatMap((a) =>
      RATIO_SNAP_TOKENS.filter((b) => Math.abs(a + b - 100) < 1e-9).map(
        (b) => [a, b] as const,
      ),
    )
    const best = pairs.reduce((acc, pair) =>
      Math.abs(pair[0] - pct) < Math.abs(acc[0] - pct) ? pair : acc,
    )
    if (Math.abs(best[0] - pct) <= RATIO_SNAP_TOLERANCE) {
      return [best[0], best[1]]
    }
    return [pct, 100 - pct]
  }
  const sum = ratios.reduce((a, b) => a + b, 0)
  if (sum <= 0) return Array.from({ length: n }, () => 100 / n)
  if (sumsTo100(sum)) return [...ratios]
  return ratios.map((r) => (r / sum) * 100)
}

/** 已经以 100 为基准时跳过除乘，避免每次保存都引入浮点抖动 */
function sumsTo100(total: number): boolean {
  return Math.abs(total - 100) < 1e-9
}

/** 拖动第 leftIndex|leftIndex+1 分隔线时，按归一化 x 重算整行 ratios */
export function ratiosFromDividerDrag(args: {
  ratios: number[]
  leftIndex: number
  /** 指针在行内容区的相对位置 0..1 */
  t: number
  /**
   * 左/右侧在 pair 内的最小份额 0..1。
   * spacer 侧传 0，才能拖回通栏原位；内容侧默认约 5%。
   */
  minLeft?: number
  minRight?: number
}): number[] {
  const { ratios, leftIndex, t } = args
  const n = ratios.length
  if (leftIndex < 0 || leftIndex >= n - 1) return ratios
  const minLeft = Math.max(0, args.minLeft ?? GROW_SOFT_MIN)
  const minRight = Math.max(0, args.minRight ?? GROW_SOFT_MIN)
  const clampedT = Math.max(minLeft, Math.min(1 - minRight, t))

  if (n === 2) {
    return snapRatios([clampedT * 100, (1 - clampedT) * 100])
  }

  const next = [...ratios]
  const prefix = next.slice(0, leftIndex).reduce((a, b) => a + b, 0)
  const suffix = next.slice(leftIndex + 2).reduce((a, b) => a + b, 0)
  const pairBudget = 100 - prefix - suffix
  if (pairBudget <= 0) return snapRatios(next)

  // t 是整行比例；映射到 pair 内份额
  const leftEdge = prefix / 100
  const rightEdge = (prefix + pairBudget) / 100
  const local = (clampedT - leftEdge) / Math.max(rightEdge - leftEdge, 1e-9)
  const localClamped = Math.max(minLeft, Math.min(1 - minRight, local))
  next[leftIndex] = pairBudget * localClamped
  next[leftIndex + 1] = pairBudget * (1 - localClamped)
  return snapRatios(next)
}

/** 拖动 column 内上下分隔线，重分配相邻 grow（总和不变） */
export function growsFromDividerDrag(args: {
  grows: number[]
  topIndex: number
  /** 指针在列内容区的相对位置 0..1 */
  t: number
  /** 上/下侧最小份额（相对 pair）；spacer 侧传 0 */
  minTop?: number
  minBottom?: number
}): number[] {
  const { grows, topIndex, t } = args
  const n = grows.length
  if (topIndex < 0 || topIndex >= n - 1) return grows
  const next = [...grows]
  const prefix = next.slice(0, topIndex).reduce((a, b) => a + b, 0)
  const suffix = next.slice(topIndex + 2).reduce((a, b) => a + b, 0)
  const pair = next[topIndex]! + next[topIndex + 1]!
  const total = prefix + pair + suffix
  if (total <= 0 || pair <= 0) return grows

  const minTop = Math.max(0, args.minTop ?? GROW_SOFT_MIN)
  const minBottom = Math.max(0, args.minBottom ?? GROW_SOFT_MIN)
  const clampedT = Math.max(minTop, Math.min(1 - minBottom, t))
  const topEdge = prefix / total
  const bottomEdge = (prefix + pair) / total
  const local =
    (clampedT - topEdge) / Math.max(bottomEdge - topEdge, 1e-9)
  const localClamped = Math.max(minTop, Math.min(1 - minBottom, local))
  // 用地板比例 * pair，避免绝对 GROW_MIN 把可偷高度卡死
  const topFloor = minTop === 0 ? 0 : pair * minTop
  const bottomFloor = minBottom === 0 ? 0 : pair * minBottom
  next[topIndex] = Math.max(topFloor, pair * localClamped)
  next[topIndex + 1] = Math.max(bottomFloor, pair * (1 - localClamped))
  return next
}
