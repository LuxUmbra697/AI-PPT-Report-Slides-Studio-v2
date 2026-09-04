import { createContext } from 'react'
import type { UiThemeId } from '@/features/ui/uiThemes'

export type UiThemeContextValue = {
  themeId: UiThemeId
  setThemeId: (themeId: UiThemeId) => void
}

export const UiThemeContext = createContext<UiThemeContextValue | null>(null)
