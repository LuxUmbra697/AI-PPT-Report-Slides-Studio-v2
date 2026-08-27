import type { components } from '@/api/schema'
import { getTheme, themeList } from '@/render/design'
import type { Theme } from '@/render/types'

type Fonts = components['schemas']['Fonts']
type FontFamily = components['schemas']['FontFamily']

export type ThemeOverrides = {
  palette?: Partial<{
    background: string
    surface: string
    ink: string
    ink_soft: string
    ink_muted: string
    accent: string
    accent_soft: string
    line: string
    line_strong: string
  }>
  fonts?: Fonts
  text_styles?: Partial<
    Record<'display' | 'title' | 'body' | 'bullet', { size_pt?: number }>
  >
  shape?: {
    radius_pt?: number
    bullet_marker?: 'rule' | 'dot' | 'index'
  }
}

export const PALETTE_KEYS = [
  { key: 'background', label: '背景' },
  { key: 'surface', label: '表面' },
  { key: 'ink', label: '主文字' },
  { key: 'ink_soft', label: '次文字' },
  { key: 'accent', label: '强调色' },
  { key: 'accent_soft', label: '强调浅底' },
  { key: 'line', label: '分割线' },
] as const

export type PaletteKey = (typeof PALETTE_KEYS)[number]['key']

export const SIZE_KEYS = [
  { key: 'display', label: '封面大标题' },
  { key: 'title', label: '页标题' },
  { key: 'body', label: '正文' },
  { key: 'bullet', label: '要点' },
] as const

export type SizeKey = (typeof SIZE_KEYS)[number]['key']

export const BULLET_MARKERS: Array<{
  value: 'rule' | 'dot' | 'index'
  label: string
}> = [
  { value: 'rule', label: '短线' },
  { value: 'dot', label: '圆点' },
  { value: 'index', label: '序号' },
]

/** 精选字体对：取自预设主题；字体组合相同的主题合并成一项，避免下拉里出现两条一模一样的选项 */
export const FONT_PRESETS: Array<{ id: string; label: string; fonts: Fonts }> = themeList.reduce<
  Array<{ id: string; label: string; fonts: Fonts }>
>((presets, theme) => {
  if (presets.some((preset) => sameFonts(preset.fonts, theme.fonts))) return presets
  presets.push({ id: theme.id, label: theme.name, fonts: theme.fonts })
  return presets
}, [])

function sameFonts(a: Fonts, b: Fonts): boolean {
  return (
    sameFamily(a.display, b.display) &&
    sameFamily(a.body, b.body)
  )
}

function sameFamily(a: FontFamily, b: FontFamily): boolean {
  return (
    a.web === b.web &&
    a.pptx_latin === b.pptx_latin &&
    a.pptx_east_asian === b.pptx_east_asian
  )
}

export function matchFontPresetId(fonts: Fonts | undefined): string | null {
  if (!fonts) return null
  const hit = FONT_PRESETS.find((preset) => sameFonts(preset.fonts, fonts))
  return hit?.id ?? null
}

export function resolveTheme(
  themeId: string,
  overrides?: ThemeOverrides | null,
): Theme {
  const base = structuredClone(getTheme(themeId))
  if (!overrides || Object.keys(overrides).length === 0) return base

  if (overrides.palette) {
    for (const [key, value] of Object.entries(overrides.palette)) {
      if (typeof value === 'string') {
        ;(base.palette as Record<string, unknown>)[key] = value
      }
    }
    if (overrides.palette.accent && base.palette.chart_series.length > 0) {
      base.palette.chart_series = [
        overrides.palette.accent,
        ...base.palette.chart_series.slice(1),
      ]
    }
  }

  if (overrides.fonts) {
    base.fonts = structuredClone(overrides.fonts)
  }

  if (overrides.text_styles) {
    for (const name of SIZE_KEYS.map((item) => item.key)) {
      const size = overrides.text_styles[name]?.size_pt
      if (size != null && base.text_styles[name]) {
        base.text_styles[name] = { ...base.text_styles[name], size_pt: size }
      }
    }
  }

  if (overrides.shape) {
    if (overrides.shape.radius_pt != null) {
      base.shape.radius_pt = overrides.shape.radius_pt
    }
    if (overrides.shape.bullet_marker != null) {
      base.shape.bullet_marker = overrides.shape.bullet_marker
    }
  }

  return base
}
