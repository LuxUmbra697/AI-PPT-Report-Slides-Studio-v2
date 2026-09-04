import { type ReactNode, useEffect, useMemo, useState } from 'react'
import {
  DEFAULT_UI_THEME_ID,
  isUiThemeId,
  type UiThemeId,
} from '@/features/ui/uiThemes'
import { UiThemeContext } from '@/features/ui/uiThemeStore'

const STORAGE_KEY = 'luxumbra-ui-theme'

function initialTheme(): UiThemeId {
  const stored = window.localStorage.getItem(STORAGE_KEY)
  return isUiThemeId(stored) ? stored : DEFAULT_UI_THEME_ID
}

export function UiThemeProvider({ children }: { children: ReactNode }) {
  const [themeId, setThemeId] = useState<UiThemeId>(initialTheme)

  useEffect(() => {
    document.documentElement.dataset.uiTheme = themeId
    window.localStorage.setItem(STORAGE_KEY, themeId)
  }, [themeId])

  const value = useMemo(() => ({ themeId, setThemeId }), [themeId])
  return <UiThemeContext.Provider value={value}>{children}</UiThemeContext.Provider>
}
