import { BookOpenText, Flame, Flower2, Orbit, RadioTower, Sparkles } from 'lucide-react'
import { type CSSProperties, useState } from 'react'
import { useUiTheme } from '@/features/ui/useUiTheme'
import type { UiThemeId } from '@/features/ui/uiThemes'

const ICONS = {
  sakura: Flower2,
  neon: RadioTower,
  shrine: Sparkles,
  celestial: BookOpenText,
  foxfire: Flame,
} satisfies Record<UiThemeId, typeof Orbit>

const LABELS: Record<UiThemeId, string[]> = {
  sakura: ['樱花结界展开', '星砂补充完毕', '今日幸运色：草莓粉'],
  neon: ['次元信号已增强', 'HUD 扫描完成', '霓虹粒子已释放'],
  shrine: ['御守带来好灵感', '风铃响了一下', '樱签：大吉'],
  celestial: ['星轨重新校准', '翻到灵感那一页', '发现一颗标题星'],
  foxfire: ['狐火点亮画布', '夜祭灯笼亮起', '扇风带来新点子'],
}

export function AnimeDecorLayer() {
  const { themeId } = useUiTheme()
  const [pulse, setPulse] = useState(0)
  const Icon = ICONS[themeId]
  const message = LABELS[themeId][pulse % LABELS[themeId].length]

  return (
    <>
      <div key={`${themeId}-${pulse}`} className={`anime-decor-layer decor-${themeId}`} aria-hidden>
        {Array.from({ length: 18 }, (_, index) => (
          <i
            key={index}
            style={{ '--decor-index': index, left: `${(index * 37) % 96}%` } as CSSProperties}
          />
        ))}
        <span className="decor-orbit"><Orbit /></span>
        <span className="decor-corner-card">LUX · {String(pulse + 1).padStart(2, '0')}</span>
      </div>
      <button
        type="button"
        className={`anime-charm-widget charm-${themeId}`}
        onClick={() => setPulse((value) => value + 1)}
        title="点击释放主题特效"
      >
        <span><Icon /></span>
        <small>{message}</small>
      </button>
    </>
  )
}
