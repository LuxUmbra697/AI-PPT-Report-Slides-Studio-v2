import { type ReactNode, useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/utils'

/**
 * 轻量下拉菜单：触发器 + 浮层，点击外部或按 Esc 关闭。
 *
 * trigger 拿到的 open 只用于表达按钮态；开合由本组件持有，调用方不必各自
 * 复制一份「点空白处关掉」的监听。
 */
export function MenuPopover({
  trigger,
  children,
  align = 'right',
  className,
  label,
}: {
  trigger: (props: { open: boolean; toggle: () => void }) => ReactNode
  children: (props: { close: () => void }) => ReactNode
  align?: 'left' | 'right'
  className?: string
  label?: string
}) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onPointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointer)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointer)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  return (
    <div ref={rootRef} className="relative">
      {trigger({ open, toggle: () => setOpen((value) => !value) })}
      {open && (
        <div
          role="menu"
          aria-label={label}
          className={cn(
            'absolute top-full z-40 mt-2 overflow-hidden rounded-2xl border border-line bg-surface shadow-pop',
            align === 'right' ? 'right-0' : 'left-0',
            className,
          )}
        >
          {children({ close: () => setOpen(false) })}
        </div>
      )}
    </div>
  )
}

export function MenuItem({
  children,
  hint,
  icon: Icon,
  disabled,
  danger,
  onSelect,
}: {
  children: ReactNode
  hint?: string
  icon?: React.ComponentType<{ className?: string }>
  disabled?: boolean
  danger?: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      role="menuitem"
      disabled={disabled}
      onClick={onSelect}
      className={cn(
        'flex w-full items-start gap-2.5 px-4 py-2.5 text-left text-[13px] transition-colors disabled:opacity-50',
        danger
          ? 'text-negative hover:bg-negative/8'
          : 'text-ink-soft hover:bg-surface-soft hover:text-ink',
      )}
    >
      {Icon && <Icon className="mt-0.5 size-3.5 shrink-0" />}
      <span className="min-w-0 flex-1">
        {children}
        {hint && <span className="mt-0.5 block text-xs text-ink-muted">{hint}</span>}
      </span>
    </button>
  )
}
