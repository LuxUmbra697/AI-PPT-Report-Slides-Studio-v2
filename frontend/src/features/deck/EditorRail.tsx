import { Image as ImageIcon, LayoutTemplate, Palette, Wand2 } from 'lucide-react'
import { AiEditPanel } from '@/features/deck/AiEditPanel'
import type { RailTab } from '@/features/deck/editorTypes'
import { ImagePanel } from '@/features/deck/ImagePanel'
import { LayoutPanel } from '@/features/deck/LayoutPanel'
import { ThemePanel } from '@/features/deck/ThemePanel'
import type { DeckSlide } from '@/features/deck/types'
import type { ProjectDetail } from '@/features/projects/types'
import { cn } from '@/lib/utils'
import type { Theme } from '@/render/types'

const RAIL_TABS: Array<{ tab: RailTab; label: string; icon: typeof Wand2 }> = [
  { tab: 'ai', label: 'AI 修改', icon: Wand2 },
  { tab: 'theme', label: '主题', icon: Palette },
  { tab: 'layout', label: '版式', icon: LayoutTemplate },
  { tab: 'image', label: '图片', icon: ImageIcon },
]

export function EditorRail({
  project,
  slide,
  theme,
  tab,
  locked,
  selectedBlockId,
  onTab,
  onOpenRelayout,
}: {
  project: ProjectDetail
  slide: DeckSlide
  theme: Theme
  tab: RailTab | null
  locked: boolean
  selectedBlockId: string | null
  onTab: (tab: RailTab) => void
  onOpenRelayout: () => void
}) {
  const panelOpen = Boolean(tab)

  return (
    <div className="flex shrink-0">
      {panelOpen && (
        <aside className="scrollbar-slim w-80 overflow-y-auto border-l border-line bg-surface px-4 py-4">
          {tab === 'ai' && <AiEditPanel projectId={project.id} slide={slide} />}
          {tab === 'theme' && <ThemePanel project={project} disabled={locked} />}
          {tab === 'layout' && (
            <LayoutPanel
              projectId={project.id}
              slide={slide}
              theme={theme}
              selectedBlockId={selectedBlockId}
              disabled={locked}
              onOpenRelayout={onOpenRelayout}
            />
          )}
          {tab === 'image' && (
            <ImagePanel projectId={project.id} slide={slide} disabled={locked} />
          )}
        </aside>
      )}

      <div className="flex w-13 flex-col items-center gap-1.5 border-l border-line bg-surface py-3">
        {RAIL_TABS.map(({ tab: value, label, icon: Icon }) => (
          <button
            key={value}
            type="button"
            title={label}
            aria-label={label}
            aria-pressed={tab === value}
            onClick={() => onTab(value)}
            className={cn(
              'grid size-9 place-items-center rounded-xl transition-colors',
              tab === value
                ? 'bg-accent-soft text-accent'
                : 'text-ink-muted hover:bg-surface-soft hover:text-ink',
            )}
          >
            <Icon className="size-4.5" />
          </button>
        ))}
      </div>
    </div>
  )
}
