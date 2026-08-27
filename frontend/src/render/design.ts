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

const themeModules = import.meta.glob<Theme>('../../../shared/themes/*.json', {
  eager: true,
  import: 'default',
})

function byId<T extends { id: string }>(modules: Record<string, T>): Map<string, T> {
  return new Map(Object.values(modules).map((item) => [item.id, item]))
}

export const layouts = byId(layoutModules)
export const themes = byId(themeModules)

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
