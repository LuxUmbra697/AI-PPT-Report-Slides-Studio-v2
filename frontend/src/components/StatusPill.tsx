import type { Project } from '@/features/projects/types'
import { cn } from '@/lib/utils'

type Status = Project['status']

/** 状态一律用用户语言表达，不暴露后端枚举 */
const STATUS: Record<Status, { label: string; className: string; pulse?: boolean }> = {
  draft: { label: '草稿', className: 'bg-surface-soft text-ink-muted' },
  outline_ready: { label: '大纲已确认', className: 'bg-accent-soft text-accent' },
  generating: { label: '生成中', className: 'bg-accent-soft text-accent', pulse: true },
  ready: { label: '可编辑', className: 'bg-positive/10 text-positive' },
}

export function StatusPill({ status, className }: { status: Status; className?: string }) {
  const { label, className: tone, pulse } = STATUS[status]

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium',
        tone,
        className,
      )}
    >
      {pulse && <span className="size-1.5 animate-pulse rounded-full bg-current" />}
      {label}
    </span>
  )
}
