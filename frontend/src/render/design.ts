import type { Layout, Theme } from '@/render/types'

/**
 * 布局与主题直接从仓库根的 shared/ 加载，与后端读的是同一批文件。
 * 走构建期 glob 而不是运行时接口，是为了让"两端各维护一套排版规则"
 * 在物理上不可能发生。
 */
const layoutModules = import.meta.glob<Layout>('../../../shared/layouts/*.json', {
  eager: true,
  import: 'default',
})

const themeModules = import.meta.glob<Theme>([
  '../../../shared/themes/*.json',
  '!../../../shared/themes/catalog.json',
  '!../../../shared/themes/visuals.json',
], {
  eager: true,
  import: 'default',
})

type CatalogPreset = {
  id: string
  name: string
  description: string
  category?: string
  base: string
  palette?: Partial<Theme['palette']>
  shape?: Partial<Theme['shape']>
  ambient?: Theme['ambient']
}

type ThemeCatalog = { presets?: CatalogPreset[] }

type VisualFamily = {
  cover_variant?: NonNullable<Theme['visual']>['cover_variant']
  content_variant?: NonNullable<Theme['visual']>['content_variant']
  transition?: NonNullable<Theme['visual']>['transition']
  ambient?: NonNullable<Theme['ambient']>
}

type VisualCatalog = {
  active_theme_ids?: string[]
  families?: Record<string, VisualFamily>
  category_families?: Record<string, string>
  preset_families?: Record<string, string>
}

const catalogModules = import.meta.glob<ThemeCatalog>('../../../shared/themes/catalog.json', {
  eager: true,
  import: 'default',
})

const visualModules = import.meta.glob<VisualCatalog>('../../../shared/themes/visuals.json', {
  eager: true,
  import: 'default',
})

function byId<T extends { id: string }>(modules: Record<string, T>): Map<string, T> {
  return new Map(Object.values(modules).map((item) => [item.id, item]))
}

export const layouts = byId(layoutModules)

const baseThemes: Theme[] = Object.values(themeModules) as Theme[]
const catalog = Object.values(catalogModules).flatMap((item) => item.presets ?? [])
const visualCatalog = Object.values(visualModules)[0] ?? {}

const activeThemeIds = new Set(visualCatalog.active_theme_ids ?? [])
const activeBaseThemes = activeThemeIds.size
  ? baseThemes.filter((theme) => activeThemeIds.has(theme.id))
  : baseThemes
const activeCatalog = activeThemeIds.size
  ? catalog.filter((preset) => activeThemeIds.has(preset.id))
  : catalog

const catalogThemes: Theme[] = activeCatalog.map((preset) => {
  const base = baseThemes.find((theme) => theme.id === preset.base)
  if (!base) throw new Error(`主题 ${preset.id} 引用了未知底座：${preset.base}`)
  const familyId =
    visualCatalog.preset_families?.[preset.id] ??
    visualCatalog.category_families?.[preset.category ?? ''] ??
    'classic'
  const family = visualCatalog.families?.[familyId]
  return {
    ...structuredClone(base),
    id: preset.id,
    name: preset.name,
    description: preset.description,
    palette: { ...base.palette, ...preset.palette },
    shape: { ...base.shape, ...preset.shape },
    ambient: [
      ...(preset.ambient ?? base.ambient ?? []),
      ...(family?.ambient ?? []),
    ],
    visual: {
      family: familyId,
      cover_variant: family?.cover_variant ?? 'editorial',
      content_variant: family?.content_variant ?? 'clean',
      transition: family?.transition ?? 'fade',
    },
  }
})

export const themes = new Map<string, Theme>(
  [...activeBaseThemes, ...catalogThemes].map((theme) => [theme.id, theme]),
)

export const themeCategoryById = new Map<string, string>([
  ...activeBaseThemes.map((theme) => [theme.id, '经典预设'] as const),
  ...activeCatalog.map((preset) => [preset.id, preset.category ?? '扩展预设'] as const),
])

export const themeCategories = [...new Set(themeCategoryById.values())]

export function getThemeCategory(themeId: string): string {
  return themeCategoryById.get(themeId) ?? '扩展预设'
}

export const themeList = [...themes.values()]

export function getLayout(layoutId: string): Layout {
  const layout = layouts.get(layoutId)
  if (!layout) throw new Error(`未知布局：${layoutId}`)
  return layout
}

export function getTheme(themeId: string): Theme {
  const theme = themes.get(themeId)
  if (!theme) throw new Error(`未知主题：${themeId}`)
  return theme
}
