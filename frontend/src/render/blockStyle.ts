import type { CSSProperties } from 'react'
import type { components } from '@/api/schema'
import { pt, resolveColor, textStyleToCss } from '@/render/style'
import type { ColorToken, TextStyleName, Theme } from '@/render/types'

export type BlockStyle = components['schemas']['BlockStyle']

/** 工具条色板：令牌 + 短标签，方便点选 */
export const COLOR_SWATCHES: Array<{ key: ColorToken; label: string }> = [
  { key: 'ink', label: '主文字' },
  { key: 'ink_soft', label: '次文字' },
  { key: 'ink_muted', label: '弱文字' },
  { key: 'accent', label: '强调' },
  { key: 'accent_soft', label: '强调底' },
  { key: 'background', label: '背景' },
  { key: 'surface', label: '表面' },
  { key: 'line', label: '分割线' },
  { key: 'line_strong', label: '深线' },
]

const HEX = /^#[0-9A-Fa-f]{6}$/

export function isHexColor(value: string): boolean {
  return HEX.test(value)
}

export function resolveColorValue(theme: Theme, value: string): string {
  if (isHexColor(value)) return value.toUpperCase()
  return resolveColor(theme, value)
}

export function mergeTextCss(
  theme: Theme,
  styleName: TextStyleName,
  style?: BlockStyle | null,
): CSSProperties {
  const base = textStyleToCss(theme, styleName)
  if (!style) return base

  const next: CSSProperties = { ...base }
  if (style.size_pt != null) next.fontSize = pt(style.size_pt)
  if (style.color != null) next.color = resolveColorValue(theme, style.color)
  if (style.weight != null) next.fontWeight = style.weight
  if (style.italic != null) next.fontStyle = style.italic ? 'italic' : 'normal'
  if (style.align != null) next.textAlign = style.align
  return next
}

export function boxCss(theme: Theme, style?: BlockStyle | null): CSSProperties {
  if (!style) return {}

  const css: CSSProperties = {
    boxSizing: 'border-box',
    width: '100%',
    height: '100%',
  }

  if (style.fill != null && style.fill !== 'none') {
    css.background = resolveColorValue(theme, style.fill)
  }
  if (style.radius_pt != null) {
    css.borderRadius = pt(style.radius_pt)
  }
  if (
    style.border_color != null &&
    style.border_width_pt != null &&
    style.border_width_pt > 0
  ) {
    css.border = `${pt(style.border_width_pt)} solid ${resolveColorValue(theme, style.border_color)}`
  }
  if (style.padding_pt != null && style.padding_pt > 0) {
    css.padding = pt(style.padding_pt)
  }
  return css
}

export function isStyleEmpty(style?: BlockStyle | null): boolean {
  if (!style) return true
  return Object.values(style).every((value) => value == null)
}

/** 按块类型决定工具条开放哪些控件 */
export type StyleCapability = {
  text: boolean
  box: boolean
  borderOnly: boolean
}

export function styleCapability(
  type: 'text' | 'bullets' | 'image' | 'chart' | 'table' | 'kpi' | 'cards' | 'callout',
): StyleCapability {
  if (type === 'chart') return { text: false, box: false, borderOnly: false }
  if (type === 'image') return { text: false, box: false, borderOnly: true }
  if (type === 'table') return { text: true, box: false, borderOnly: false }
  return { text: true, box: true, borderOnly: false }
}

export function patchStyle(
  current: BlockStyle | null | undefined,
  patch: Partial<BlockStyle>,
): BlockStyle | null {
  const next: BlockStyle = { ...(current ?? {}), ...patch }
  // 显式 null 表示清除该字段
  for (const [key, value] of Object.entries(next)) {
    if (value == null) delete next[key as keyof BlockStyle]
  }
  return isStyleEmpty(next) ? null : next
}
