import { Loader2, RefreshCw, Undo2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useProposeRelayout } from '@/features/deck/api'
import { getSlideSaveHandlers } from '@/features/deck/slideSaveBridge'
import type { DeckSlide, RelayoutCandidate, RelayoutProposal } from '@/features/deck/types'
import { toRenderSlide } from '@/features/deck/types'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'
import type { FlexContainer } from '@/render/flexLayout'
import { SlideThumbnail } from '@/render/SlideView'
import type { Theme } from '@/render/types'

/**
 * 「换排布」右侧面板：点缩略图即应用候选布局树，Undo 恢复上一棵。
 */
export function RelayoutDock({
  projectId,
  slide,
  theme,
  open,
  disabled,
  onClose,
}: {
  projectId: string
  slide: DeckSlide
  theme: Theme
  open: boolean
  disabled?: boolean
  onClose: () => void
}) {
  const propose = useProposeRelayout(projectId, slide.id)
  const [proposal, setProposal] = useState<RelayoutProposal | null>(null)
  const [appliedId, setAppliedId] = useState<string | null>(null)
  const [undoTree, setUndoTree] = useState<FlexContainer | null>(null)
  const [originalTree, setOriginalTree] = useState<FlexContainer | null>(null)

  useEffect(() => {
    if (!open) return
    setProposal(null)
    setAppliedId(null)
    setUndoTree(null)
    const current = (slide.layout_tree as FlexContainer | null) ?? null
    setOriginalTree(current ? structuredClone(current) : null)
    propose.mutate(
      { revision: slide.revision },
      {
        onSuccess: (data) => setProposal(data),
      },
    )
    // 仅在打开时拉取；slide.revision 变化由 apply 后外层刷新
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, projectId, slide.id])

  if (!open) return null

  const applyTree = (tree: FlexContainer, candidateId: string | null) => {
    const handlers = getSlideSaveHandlers(slide.id)
    if (!handlers) return
    const previous = (slide.layout_tree as FlexContainer | null) ?? null
    if (previous) setUndoTree(structuredClone(previous))
    setAppliedId(candidateId)
    handlers.commitFlex(tree)
  }

  const undo = () => {
    if (!undoTree) return
    const handlers = getSlideSaveHandlers(slide.id)
    if (!handlers) return
    handlers.commitFlex(undoTree)
    setUndoTree(null)
    setAppliedId(null)
  }

  const showMore = () => {
    propose.mutate(
      { revision: slide.revision },
      {
        onSuccess: (data) => {
          setProposal((current) => {
            if (!current) return data
            const seen = new Set(current.candidates.map((c) => c.id))
            const merged = [...current.candidates]
            for (const candidate of data.candidates) {
              if (!seen.has(candidate.id)) merged.push(candidate)
            }
            return { revision: data.revision, candidates: merged }
          })
        },
      },
    )
  }

  const candidates = proposal?.candidates ?? []

  return (
    <aside
      className="flex h-full w-80 shrink-0 flex-col border-l border-line bg-surface shadow-card"
      aria-label="换排布"
    >
      <div className="flex items-center gap-2 border-b border-line px-4 py-3">
        <h2 className="flex-1 text-[14px] font-semibold">换排布</h2>
        <button
          type="button"
          disabled={!undoTree || disabled}
          onClick={undo}
          className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[12px] text-ink-soft hover:bg-surface-soft disabled:opacity-35"
        >
          <Undo2 className="size-3.5" />
          撤销
        </button>
        <button
          type="button"
          aria-label="关闭"
          onClick={onClose}
          className="rounded-lg p-1.5 text-ink-muted hover:bg-surface-soft hover:text-ink"
        >
          <X className="size-4" />
        </button>
      </div>

      <div className="scrollbar-slim flex-1 space-y-3 overflow-y-auto p-3">
        {propose.isPending && !proposal && (
          <p className="flex items-center gap-2 px-1 py-6 text-[13px] text-ink-muted">
            <Loader2 className="size-3.5 animate-spin" />
            正在生成排布…
          </p>
        )}
        {propose.isError && (
          <p role="alert" className="text-xs text-negative">
            {errorMessage(propose.error, '生成排布失败')}
          </p>
        )}
        {originalTree && (
          <CandidateCard
            label="当前"
            selected={appliedId == null}
            slide={slide}
            theme={theme}
            tree={originalTree}
            disabled={disabled}
            onSelect={() => applyTree(originalTree, null)}
          />
        )}

        {candidates.map((candidate, index) => (
          <CandidateCard
            key={candidate.id}
            label={`方案 ${index + 1}`}
            selected={appliedId === candidate.id}
            slide={slide}
            theme={theme}
            tree={candidate.layout_tree}
            disabled={disabled}
            onSelect={() => applyTree(candidate.layout_tree, candidate.id)}
          />
        ))}
      </div>

      <div className="border-t border-line p-3">
        <button
          type="button"
          disabled={disabled || propose.isPending}
          onClick={showMore}
          className="flex w-full items-center justify-center gap-2 rounded-xl border border-line px-3 py-2.5 text-[13px] text-ink-soft transition-colors hover:bg-surface-soft disabled:opacity-50"
        >
          {propose.isPending ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <RefreshCw className="size-3.5" />
          )}
          显示更多
        </button>
      </div>
    </aside>
  )
}

/** 版式面板内的轻量入口：打开 dock */
export function RelayoutOpenButton({
  disabled,
  onOpen,
}: {
  disabled?: boolean
  onOpen: () => void
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onOpen}
      className="flex w-full items-center gap-2 rounded-xl border border-line px-3.5 py-3 text-left transition-colors hover:border-line-strong hover:bg-surface-soft disabled:opacity-50"
    >
      <RefreshCw className="size-3.5 shrink-0 text-accent" />
      <span>
        <span className="block text-[13px] font-medium">换一种排布</span>
        <span className="mt-0.5 block text-xs leading-relaxed text-ink-muted">
          内容不变，挑选更合适的版面
        </span>
      </span>
    </button>
  )
}

function CandidateCard({
  label,
  selected,
  slide,
  theme,
  tree,
  disabled,
  onSelect,
}: {
  label: string
  selected: boolean
  slide: DeckSlide
  theme: Theme
  tree: FlexContainer | RelayoutCandidate['layout_tree']
  disabled?: boolean
  onSelect: () => void
}) {
  const preview = toRenderSlide({
    ...slide,
    layout_mode: 'flex',
    layout_tree: tree as DeckSlide['layout_tree'],
  })
  return (
    <button
      type="button"
      aria-pressed={selected}
      disabled={disabled}
      onClick={onSelect}
      className={cn(
        'w-full rounded-xl border p-2 text-left transition-colors disabled:opacity-50',
        selected
          ? 'border-accent bg-accent-soft/40'
          : 'border-line hover:border-line-strong',
      )}
    >
      <span className="mb-2 block text-[12px] font-medium text-ink-soft">{label}</span>
      <div className="pointer-events-none overflow-hidden rounded-lg">
        <SlideThumbnail slide={preview} theme={theme} />
      </div>
    </button>
  )
}
