import { Check, ChevronDown } from 'lucide-react'
import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from 'react'
import { cn } from '@/lib/utils'

export interface PillSelectOption {
  value: string | number
  label: string
  /** 菜单里可选的一行弱说明 */
  description?: string
}

interface PillSelectProps {
  label: string
  value: string | number
  options: ReadonlyArray<PillSelectOption>
  onChange: (value: string) => void
  disabled?: boolean
  className?: string
  /** 触发器额外内容，例如小图标 */
  leading?: ReactNode
}

/**
 * Gamma 风格参数胶囊：轻量触发器 + 浮动菜单。
 * 不用原生 select，避免系统蓝底选中块。
 */
export function PillSelect({
  label,
  value,
  options,
  onChange,
  disabled = false,
  className,
  leading,
}: PillSelectProps) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const listId = useId()
  const selected = options.find((option) => String(option.value) === String(value))
  const selectedIndex = Math.max(
    0,
    options.findIndex((option) => String(option.value) === String(value)),
  )

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const active = listRef.current?.querySelector<HTMLElement>('[data-active="true"]')
    active?.scrollIntoView({ block: 'nearest' })
  }, [open, selectedIndex])

  const pick = (next: string | number) => {
    onChange(String(next))
    setOpen(false)
  }

  const onTriggerKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return
    if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      setOpen(true)
    }
  }

  const onListKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const delta = event.key === 'ArrowDown' ? 1 : -1
      const next = (selectedIndex + delta + options.length) % options.length
      onChange(String(options[next]!.value))
      return
    }
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      setOpen(false)
    }
  }

  return (
    <div ref={rootRef} className={cn('relative', className)}>
      <button
        type="button"
        disabled={disabled}
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={onTriggerKeyDown}
        className={cn(
          'group inline-flex h-9 items-center gap-1.5 rounded-full px-3.5',
          'bg-surface-soft/90 text-[13px] font-medium text-ink-soft',
          'ring-1 ring-transparent transition-all duration-150',
          'hover:bg-white hover:text-ink hover:ring-line hover:shadow-sm',
          open && 'bg-white text-ink shadow-sm ring-line',
          'disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:bg-surface-soft/90 disabled:hover:shadow-none disabled:hover:ring-transparent',
        )}
      >
        {leading}
        <span className="max-w-36 truncate">{selected?.label ?? String(value)}</span>
        <ChevronDown
          className={cn(
            'size-3.5 shrink-0 text-ink-muted transition-transform duration-200',
            open && 'rotate-180 text-ink-soft',
          )}
        />
      </button>

      {open && (
        <div
          ref={listRef}
          id={listId}
          role="listbox"
          aria-label={label}
          tabIndex={-1}
          onKeyDown={onListKeyDown}
          className={cn(
            'absolute top-[calc(100%+6px)] left-0 z-50 min-w-[11.5rem] outline-none',
            'origin-top-left animate-in',
            'rounded-2xl border border-line/80 bg-white/95 p-1.5 shadow-pop backdrop-blur-md',
          )}
        >
          <div className="max-h-64 overflow-y-auto overscroll-contain py-0.5">
            {options.map((option) => {
              const active = String(option.value) === String(value)
              return (
                <button
                  key={String(option.value)}
                  type="button"
                  role="option"
                  aria-selected={active}
                  data-active={active || undefined}
                  onClick={() => pick(option.value)}
                  className={cn(
                    'flex w-full items-start gap-2.5 rounded-xl px-2.5 py-2 text-left transition-colors',
                    active
                      ? 'bg-surface-soft text-ink'
                      : 'text-ink-soft hover:bg-canvas hover:text-ink',
                  )}
                >
                  <span
                    className={cn(
                      'mt-0.5 grid size-4 shrink-0 place-items-center rounded-full',
                      active ? 'bg-ink text-white' : 'bg-transparent',
                    )}
                  >
                    {active ? <Check className="size-2.5 stroke-[2.5]" /> : null}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13px] font-medium leading-snug">
                      {option.label}
                    </span>
                    {option.description ? (
                      <span className="mt-0.5 block text-[11px] leading-snug text-ink-muted">
                        {option.description}
                      </span>
                    ) : null}
                  </span>
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
