import { useContext } from 'react'
import { UiThemeContext, type UiThemeContextValue } from '@/features/ui/uiThemeStore'

export function useUiTheme(): UiThemeContextValue {
  const context = useContext(UiThemeContext)
  if (!context) throw new Error('useUiTheme 必须在 UiThemeProvider 内使用')
  return context
}
