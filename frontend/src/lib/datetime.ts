const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

/** 列表里的时间只用于判断"新旧"，精确到分钟没有意义，越短越好读 */
export function relativeTime(iso: string): string {
  const target = new Date(iso).getTime()
  if (Number.isNaN(target)) return ''

  const diff = Date.now() - target
  if (diff < MINUTE) return '刚刚'
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)} 分钟前`
  if (diff < DAY) return `${Math.floor(diff / HOUR)} 小时前`
  if (diff < 7 * DAY) return `${Math.floor(diff / DAY)} 天前`

  return new Date(iso).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
}
