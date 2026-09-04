export type UiThemeId = 'sakura' | 'neon' | 'shrine' | 'celestial' | 'foxfire'

export type UiTheme = {
  id: UiThemeId
  name: string
  label: string
  description: string
  mascotAsset: string
  mascotName: string
  colors: readonly [string, string, string]
}

/** 产品界面主题。它们只改变 Web 工作台，不会影响 PPT 的导出配色。 */
export const UI_THEMES: readonly UiTheme[] = [
  {
    id: 'sakura',
    name: '樱语魔法',
    label: 'SAKURA',
    description: '糖果粉与星尘，轻盈的魔法学院感。',
    mascotAsset: '/mascots/actions/anime-sakura-actions.png',
    mascotName: '小樱露',
    colors: ['#ff5ea8', '#ffc2df', '#7657ff'],
  },
  {
    id: 'neon',
    name: '霓虹次元',
    label: 'NEON',
    description: '赛博蓝紫与发光网格，像深夜的未来街区。',
    mascotAsset: '/mascots/actions/anime-neon-actions.png',
    mascotName: '澪光',
    colors: ['#37e8ff', '#8e5cff', '#101936'],
  },
  {
    id: 'shrine',
    name: '月见神社',
    label: 'MIKOSHI',
    description: '朱红、宣纸与樱瓣，安静的和风结界。',
    mascotAsset: '/mascots/actions/anime-shrine-actions.png',
    mascotName: '结羽',
    colors: ['#d94056', '#fff5e7', '#5b2630'],
  },
  {
    id: 'celestial',
    name: '星穹书阁',
    label: 'CELESTIA',
    description: '月白与深海蓝，漂浮在星图中的阅读室。',
    mascotAsset: '/mascots/actions/anime-celestial-actions.png',
    mascotName: '露弥',
    colors: ['#5d80ff', '#bed8ff', '#293e7a'],
  },
  {
    id: 'foxfire',
    name: '狐灯夜话',
    label: 'KITSUNE',
    description: '绯红、金箔与狐火，热烈的东方幻想。',
    mascotAsset: '/mascots/actions/anime-foxfire-actions.png',
    mascotName: '茜火',
    colors: ['#e34a35', '#f6b54b', '#4c1f28'],
  },
] as const

export const DEFAULT_UI_THEME_ID: UiThemeId = 'sakura'

export function isUiThemeId(value: string | null): value is UiThemeId {
  return UI_THEMES.some((theme) => theme.id === value)
}

export function getUiTheme(id: UiThemeId): UiTheme {
  return UI_THEMES.find((theme) => theme.id === id) ?? UI_THEMES[0]
}
