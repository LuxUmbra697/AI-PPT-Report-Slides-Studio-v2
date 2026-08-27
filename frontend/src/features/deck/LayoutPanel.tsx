import { Check, Loader2, Unlock } from 'lucide-react'
import {
  useSlideLayouts,
  useSwitchSlideLayout,
  useUnlockSlideFlex,
} from '@/features/deck/api'
import { BlockInsertPanel } from '@/features/deck/BlockInsertRail'
import { RelayoutOpenButton } from '@/features/deck/RelayoutPanel'
import type { DeckSlide } from '@/features/deck/types'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'
import type { Theme } from '@/render/types'

/** 版式切换：只列出这一页内容装得下的版式，装不下的给出原因而不是直接隐藏 */
export function LayoutPanel({
  projectId,
  slide,
  selectedBlockId,
  disabled,
  onOpenRelayout,
}: {
  projectId: string
  slide: DeckSlide
  theme: Theme
  selectedBlockId?: string | null
  disabled?: boolean
  onOpenRelayout?: () => void
}) {
  const layouts = useSlideLayouts(projectId, slide.id, true)
  const switchLayout = useSwitchSlideLayout(projectId, slide.id)
  const unlockFlex = useUnlockSlideFlex(projectId, slide.id)
  const options = layouts.data ?? []
  const isFlex = slide.layout_mode === 'flex'

  return (
    <div className="flex flex-col gap-2">
      {!isFlex && (
        <button
          type="button"
          disabled={disabled || unlockFlex.isPending}
          onClick={() => unlockFlex.mutate({ revision: slide.revision })}
          className="flex items-center gap-2 rounded-xl border border-dashed border-accent/40 bg-accent-soft/40 px-3.5 py-3 text-left transition-colors hover:border-accent hover:bg-accent-soft disabled:opacity-50"
        >
          {unlockFlex.isPending ? (
            <Loader2 className="size-3.5 shrink-0 animate-spin text-accent" />
          ) : (
            <Unlock className="size-3.5 shrink-0 text-accent" />
          )}
          <span>
            <span className="block text-[13px] font-medium text-accent">自由编辑此页</span>
            <span className="mt-0.5 block text-xs leading-relaxed text-ink-muted">
              可自由增删内容、拖拽调整版面
            </span>
          </span>
        </button>
      )}

      {isFlex && (
        <BlockInsertPanel
          projectId={projectId}
          slide={slide}
          selectedBlockId={selectedBlockId ?? null}
          disabled={disabled || slide.status !== 'ready'}
        />
      )}

      {isFlex && onOpenRelayout && (
        <RelayoutOpenButton
          disabled={disabled || slide.status !== 'ready'}
          onOpen={onOpenRelayout}
        />
      )}

      {layouts.isPending && (
        <p className="flex items-center gap-2 text-[13px] text-ink-muted">
          <Loader2 className="size-3.5 animate-spin" />
          正在读取可用版式…
        </p>
      )}
      {layouts.isError && (
        <p className="text-[13px] text-negative">{errorMessage(layouts.error, '版式列表加载失败')}</p>
      )}

      {!isFlex &&
        options.map((candidate) => {
          const unusable = !candidate.compatible
          return (
            <button
              key={candidate.layout_id}
              type="button"
              aria-pressed={candidate.current}
              disabled={unusable || candidate.current || disabled || switchLayout.isPending}
              onClick={() =>
                switchLayout.mutate({ layout_id: candidate.layout_id, revision: slide.revision })
              }
              className={cn(
                'rounded-xl border px-3.5 py-3 text-left transition-colors',
                candidate.current
                  ? 'border-accent bg-accent-soft'
                  : unusable
                    ? 'cursor-not-allowed border-line opacity-55'
                    : 'border-line hover:border-line-strong hover:bg-surface-soft',
              )}
            >
              <span className="flex items-center gap-2">
                <span className="flex-1 text-[13px] font-medium">{candidate.name}</span>
                {candidate.current && <Check className="size-3.5 shrink-0 text-accent" />}
              </span>
              <span className="mt-0.5 block text-xs leading-relaxed text-ink-muted">
                {unusable && candidate.reason ? candidate.reason : candidate.usage}
              </span>
            </button>
          )
        })}

      {switchLayout.isError && (
        <p role="alert" className="text-xs text-negative">
          {errorMessage(switchLayout.error, '切换失败')}
        </p>
      )}
      {unlockFlex.isError && (
        <p role="alert" className="text-xs text-negative">
          {errorMessage(unlockFlex.error, '解锁失败')}
        </p>
      )}
    </div>
  )
}
