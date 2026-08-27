import { useQueryClient } from '@tanstack/react-query'
import { Check, RotateCcw } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { useUpdateProjectTheme } from '@/features/projects/api'
import type { ProjectDetail } from '@/features/projects/types'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'
import { themeList } from '@/render/design'
import { ThemeCover } from '@/render/ThemeCover'
import {
  BULLET_MARKERS,
  FONT_PRESETS,
  matchFontPresetId,
  PALETTE_KEYS,
  type PaletteKey,
  resolveTheme,
  SIZE_KEYS,
  type SizeKey,
  type ThemeOverrides,
} from '@/render/themeOverrides'

const DEBOUNCE_MS = 320

function asOverrides(raw: ProjectDetail['theme_overrides']): ThemeOverrides {
  if (!raw || typeof raw !== 'object') return {}
  return raw as ThemeOverrides
}

/**
 * 主题微调：换预设 + 颜色/字体/字号/圆角。
 * 本地先合并出预览，防抖后写入 theme_overrides。
 */
export function ThemePanel({
  project,
  disabled,
}: {
  project: ProjectDetail
  disabled?: boolean
}) {
  const titleId = useId()
  const queryClient = useQueryClient()
  const update = useUpdateProjectTheme(project.id)
  const [draft, setDraft] = useState<ThemeOverrides>(() => asOverrides(project.theme_overrides))
  const [themeId, setThemeId] = useState(project.theme_id)
  const timerRef = useRef<number | null>(null)
  const skipNextSync = useRef(false)
  const detailKey = ['projects', project.id] as const

  const paintProject = (nextThemeId: string, nextOverrides: ThemeOverrides) => {
    queryClient.setQueryData<ProjectDetail>(detailKey, (current) =>
      current
        ? { ...current, theme_id: nextThemeId, theme_overrides: nextOverrides }
        : current,
    )
  }

  useEffect(() => {
    if (skipNextSync.current) {
      skipNextSync.current = false
      return
    }
    setThemeId(project.theme_id)
    setDraft(asOverrides(project.theme_overrides))
  }, [project.theme_id, project.theme_overrides])

  useEffect(
    () => () => {
      if (timerRef.current != null) window.clearTimeout(timerRef.current)
    },
    [],
  )

  const resolved = resolveTheme(themeId, draft)
  const fontPresetId = matchFontPresetId(draft.fonts) ?? matchFontPresetId(resolved.fonts)
  const busy = disabled

  const persistOverrides = (next: ThemeOverrides) => {
    if (timerRef.current != null) window.clearTimeout(timerRef.current)
    timerRef.current = window.setTimeout(() => {
      skipNextSync.current = true
      update.mutate({ overrides: next })
    }, DEBOUNCE_MS)
  }

  const patchDraft = (recipe: (current: ThemeOverrides) => ThemeOverrides) => {
    setDraft((current) => {
      const next = recipe(current)
      paintProject(themeId, next)
      persistOverrides(next)
      return next
    })
  }

  const selectPreset = (id: string) => {
    if (busy || id === themeId) return
    if (timerRef.current != null) window.clearTimeout(timerRef.current)
    setThemeId(id)
    setDraft({})
    paintProject(id, {})
    skipNextSync.current = true
    update.mutate({ theme_id: id, overrides: {} })
  }

  const resetOverrides = () => {
    if (busy) return
    if (timerRef.current != null) window.clearTimeout(timerRef.current)
    setDraft({})
    paintProject(themeId, {})
    skipNextSync.current = true
    update.mutate({ overrides: {} })
  }

  const setPalette = (key: PaletteKey, value: string) => {
    patchDraft((current) => ({
      ...current,
      palette: { ...current.palette, [key]: value.toUpperCase() },
    }))
  }

  const setSize = (key: SizeKey, sizePt: number) => {
    patchDraft((current) => ({
      ...current,
      text_styles: {
        ...current.text_styles,
        [key]: { size_pt: sizePt },
      },
    }))
  }

  const setFontPreset = (presetId: string) => {
    const preset = FONT_PRESETS.find((item) => item.id === presetId)
    if (!preset) return
    patchDraft((current) => ({
      ...current,
      fonts: structuredClone(preset.fonts),
    }))
  }

  const hasOverrides = Object.keys(draft).length > 0

  return (
    <section aria-labelledby={titleId} className="flex flex-col gap-5">
      <div>
        <h3 id={titleId} className="text-sm font-semibold tracking-tight">
          主题与样式
        </h3>
        <p className="mt-1 text-xs leading-relaxed text-ink-muted">
          先选一套预设，再微调颜色、字体与字号；导出 PPTX 会使用相同样式
        </p>
      </div>

      <div className="flex flex-col gap-2">
        <p className="text-xs font-medium text-ink-soft">预设</p>
        <div className="flex flex-col gap-2">
          {themeList.map((theme) => (
            <button
              key={theme.id}
              type="button"
              disabled={busy}
              aria-pressed={theme.id === themeId}
              onClick={() => selectPreset(theme.id)}
              className={cn(
                'overflow-hidden rounded-xl border text-left transition-colors',
                theme.id === themeId
                  ? 'border-accent ring-1 ring-accent/30'
                  : 'border-line hover:border-line-strong',
                'disabled:opacity-50',
              )}
            >
              <ThemeCover theme={theme} title={project.title} />
              <div className="flex items-center gap-2 px-3 py-2">
                <span className="flex-1 truncate text-[13px] font-medium">{theme.name}</span>
                {theme.id === themeId && <Check className="size-3.5 shrink-0 text-accent" />}
              </div>
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-2.5">
        <p className="text-xs font-medium text-ink-soft">颜色</p>
        <ul className="flex flex-col gap-2">
          {PALETTE_KEYS.map(({ key, label }) => (
            <li key={key} className="flex items-center gap-3">
              <label className="w-16 shrink-0 text-[12px] text-ink-muted" htmlFor={`color-${key}`}>
                {label}
              </label>
              <input
                id={`color-${key}`}
                type="color"
                disabled={busy}
                value={resolved.palette[key]}
                onChange={(event) => setPalette(key, event.target.value)}
                className="h-8 w-10 cursor-pointer rounded border border-line bg-surface p-0.5 disabled:opacity-40"
              />
              <span className="font-mono text-[11px] text-ink-muted tabular-nums">
                {resolved.palette[key]}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div className="flex flex-col gap-2">
        <label htmlFor="font-preset" className="text-xs font-medium text-ink-soft">
          字体
        </label>
        <select
          id="font-preset"
          disabled={busy}
          value={fontPresetId ?? FONT_PRESETS[0]?.id}
          onChange={(event) => setFontPreset(event.target.value)}
          className={cn(
            'h-9 rounded-xl border border-line bg-surface px-3 text-[13px] text-ink',
            'focus:border-accent focus:outline-none disabled:opacity-40',
          )}
        >
          {FONT_PRESETS.map((preset) => (
            <option key={preset.id} value={preset.id}>
              {preset.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-3">
        <p className="text-xs font-medium text-ink-soft">字号</p>
        {SIZE_KEYS.map(({ key, label }) => {
          const value = Math.round(resolved.text_styles[key]?.size_pt ?? 14)
          return (
            <label key={key} className="flex flex-col gap-1.5">
              <span className="flex items-center justify-between text-[12px] text-ink-muted">
                <span>{label}</span>
                <span className="tabular-nums">{value} pt</span>
              </span>
              <input
                type="range"
                min={8}
                max={72}
                step={1}
                disabled={busy}
                value={value}
                onChange={(event) => setSize(key, Number(event.target.value))}
                className="w-full accent-[var(--color-accent)] disabled:opacity-40"
              />
            </label>
          )
        })}
      </div>

      <div className="flex flex-col gap-3">
        <p className="text-xs font-medium text-ink-soft">形状</p>
        <label className="flex flex-col gap-1.5">
          <span className="flex items-center justify-between text-[12px] text-ink-muted">
            <span>圆角</span>
            <span className="tabular-nums">{Math.round(resolved.shape.radius_pt)} pt</span>
          </span>
          <input
            type="range"
            min={0}
            max={24}
            step={1}
            disabled={busy}
            value={Math.round(resolved.shape.radius_pt)}
            onChange={(event) =>
              patchDraft((current) => ({
                ...current,
                shape: { ...current.shape, radius_pt: Number(event.target.value) },
              }))
            }
            className="w-full accent-[var(--color-accent)] disabled:opacity-40"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="text-[12px] text-ink-muted">项目符号</span>
          <select
            disabled={busy}
            value={resolved.shape.bullet_marker}
            onChange={(event) =>
              patchDraft((current) => ({
                ...current,
                shape: {
                  ...current.shape,
                  bullet_marker: event.target.value as 'rule' | 'dot' | 'index',
                },
              }))
            }
            className={cn(
              'h-9 rounded-xl border border-line bg-surface px-3 text-[13px] text-ink',
              'focus:border-accent focus:outline-none disabled:opacity-40',
            )}
          >
            {BULLET_MARKERS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="ghost"
          size="sm"
          disabled={busy || !hasOverrides}
          onClick={resetOverrides}
        >
          <RotateCcw className="size-3.5" />
          重置微调
        </Button>
        {update.isPending && <span className="text-xs text-ink-muted">保存中…</span>}
      </div>

      {update.isError && (
        <p role="alert" className="rounded-xl bg-negative/8 px-3 py-2 text-xs text-negative">
          {errorMessage(update.error)}
        </p>
      )}
    </section>
  )
}
