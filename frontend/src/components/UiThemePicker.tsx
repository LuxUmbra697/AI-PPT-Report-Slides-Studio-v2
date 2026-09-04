import { Palette, Sparkles } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useUiTheme } from '@/features/ui/useUiTheme'
import { UI_THEMES } from '@/features/ui/uiThemes'
import { cn } from '@/lib/utils'

export function UiThemePicker() {
  const { themeId, setThemeId } = useUiTheme()
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-label="切换界面主题"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="anime-theme-trigger"
      >
        <Palette className="size-4" />
        <span className="hidden sm:inline">界面主题</span>
        <Sparkles className="size-3 text-accent" />
      </button>

      {open && (
        <div className="anime-theme-menu animate-in" role="menu" aria-label="选择界面主题">
          <div className="mb-2.5 px-1">
            <p className="text-xs font-bold tracking-[0.16em] text-accent">ANIME UI THEMES</p>
            <p className="mt-1 text-[11px] text-ink-muted">换一套配色、装饰与专属看板娘</p>
          </div>
          <div className="grid gap-1.5">
            {UI_THEMES.map((theme) => (
              <button
                key={theme.id}
                type="button"
                role="menuitemradio"
                aria-checked={theme.id === themeId}
                onClick={() => {
                  setThemeId(theme.id)
                  setOpen(false)
                }}
                className={cn('anime-theme-option', theme.id === themeId && 'is-selected')}
              >
                <span className="anime-theme-swatch" aria-hidden>
                  {theme.colors.map((color) => (
                    <i key={color} style={{ background: color }} />
                  ))}
                </span>
                <span className="min-w-0 flex-1 text-left">
                  <span className="block text-xs font-bold text-ink">{theme.name}</span>
                  <span className="mt-0.5 block truncate text-[10px] text-ink-muted">{theme.description}</span>
                </span>
                <span className="text-[9px] font-extrabold tracking-wider text-accent">{theme.label}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
