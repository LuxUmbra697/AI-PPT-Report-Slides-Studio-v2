import { AlertTriangle } from 'lucide-react'
import type { BlockSelection } from '@/features/deck/editorTypes'
import { SlidePage } from '@/features/deck/SlidePage'
import type { DeckSlide } from '@/features/deck/types'
import { useSlideVisibility } from '@/features/deck/useSlideVisibility'
import { ZoomControls } from '@/features/deck/ZoomControls'
import type { Theme } from '@/render/types'

export function SlideStage({
  projectId,
  slides,
  activeId,
  scrollRequest,
  theme,
  locked,
  zoom,
  canZoomIn,
  canZoomOut,
  selection,
  onSelectionChange,
  onActiveChange,
  onOpenRelayout,
  onZoom,
}: {
  projectId: string
  slides: DeckSlide[]
  activeId: string | null
  scrollRequest: { id: string; nonce: number } | null
  theme: Theme
  locked: boolean
  zoom: number
  canZoomIn: boolean
  canZoomOut: boolean
  selection: BlockSelection | null
  onSelectionChange: (selection: BlockSelection | null) => void
  onActiveChange: (slideId: string) => void
  onOpenRelayout: () => void
  onZoom: (delta: 1 | -1) => void
}) {
  const { scrollerRef, bindSlideEl } = useSlideVisibility({
    slides,
    scrollRequest,
    onActiveChange,
  })
  const active = slides.find((slide) => slide.id === activeId) ?? null
  const warnings =
    active?.issues.filter((issue) => issue.severity === 'warning') ?? []

  return (
    <main className="bg-stage flex min-w-0 flex-1 flex-col">
      <div ref={scrollerRef} className="scrollbar-slim flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-[96rem] flex-col items-center gap-10 px-8 py-8">
          {slides.map((slide, index) => (
            <SlidePage
              key={slide.id}
              projectId={projectId}
              slide={slide}
              theme={theme}
              locked={locked}
              zoom={zoom}
              index={index}
              total={slides.length}
              active={slide.id === activeId}
              selectedBlockId={
                selection?.slideId === slide.id ? selection.blockId : null
              }
              onSelectBlock={(blockId) =>
                onSelectionChange(blockId ? { slideId: slide.id, blockId } : null)
              }
              onOpenRelayout={onOpenRelayout}
              bindEl={bindSlideEl}
            />
          ))}
        </div>
      </div>

      <footer className="flex flex-wrap items-center gap-4 border-t border-line bg-surface/70 px-4 py-2 backdrop-blur">
        <ZoomControls
          zoom={zoom}
          canZoomIn={canZoomIn}
          canZoomOut={canZoomOut}
          onZoom={onZoom}
        />

        <span className="text-xs text-ink-muted">
          {locked
            ? '生成中暂不可编辑'
            : active?.status === 'ready'
              ? '点击元素调样式；Ctrl/⌘+Z 撤销，Ctrl/⌘+Shift+Z 重做'
              : '向下滚动查看其他页面'}
        </span>

        {warnings.length > 0 && (
          <span className="flex items-center gap-1.5 text-xs text-warning">
            <AlertTriangle className="size-3.5" />
            {warnings.length} 处内容偏长
          </span>
        )}
      </footer>
    </main>
  )
}
