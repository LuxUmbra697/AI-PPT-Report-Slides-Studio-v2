import { PAGE_COUNT_RANGE, TONE_LABEL } from '@/features/projects/types'
import { themeList, themes } from '@/render/design'

export const TONE_OPTIONS = Object.entries(TONE_LABEL).map(([value, label]) => ({ value, label }))

export const PAGE_COUNT_OPTIONS = Array.from(
  { length: PAGE_COUNT_RANGE.max - PAGE_COUNT_RANGE.min + 1 },
  (_, index) => {
    const count = PAGE_COUNT_RANGE.min + index
    return { value: count, label: `${count} 页` }
  },
)

/** 创作时先给一个确定的主题，真正的选择发生在生成前的自定义步骤 */
export const DEFAULT_THEME_ID = themes.has('ivory') ? 'ivory' : themeList[0].id
