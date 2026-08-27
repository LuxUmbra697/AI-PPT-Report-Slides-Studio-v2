import { AlertTriangle, Loader2, RefreshCw, RotateCw } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { useRetrySlide } from '@/features/deck/api'
import { ChartDataEditor } from '@/features/deck/ChartDataEditor'
import { ElementToolbar } from '@/features/deck/ElementToolbar'
import { FlexEditLayer } from '@/features/deck/FlexEditLayer'
import { findLeafParent, setContainerPreset } from '@/features/deck/flexTree'
import { registerSlideSaveHandlers } from '@/features/deck/slideSaveBridge'
import type { DeckSlide } from '@/features/deck/types'
import { toRenderSlide } from '@/features/deck/types'
import { type SaveStatus, useSlideSaveQueue } from '@/features/deck/useSlideSaveQueue'
import { cn } from '@/lib/utils'
import type { BlockStyle } from '@/render/blockStyle'
import type { FlexContainer } from '@/render/flexLayout'
import { SlideView } from '@/render/SlideView'
import type { Slide, Theme } from '@/render/types'

export function SlidePage({
  projectId,
  slide,
  theme,
  locked,
  zoom,
  index,
  total,
  active,
  selectedBlockId,
  onSelectBlock,
  onOpenRelayout,
  bindEl,
}: {
  projectId: string
  slide: DeckSlide
  theme: Theme
  locked: boolean
  zoom: number
  index: number
  total: number
  active: boolean
  selectedBlockId: string | null
  onSelectBlock: (blockId: string | null) => void
  onOpenRelayout: () => void
  bindEl: (slideId: string, node: HTMLElement | null) => void
}) {
  const {
    commit,
    commitStyle,
    commitFlex,
    commitCreateBlock,
    commitDeleteBlock,
    commitMutate,
    undo,
    redo,
    canUndo,
    canRedo,
    historyTick,
    status,
    error,
    refresh,
  } = useSlideSaveQueue(projectId, slide.id)
  const retry = useRetrySlide(projectId)
  const editable = slide.status === 'ready' && !locked && status !== 'conflict'
  const isFlex = slide.layout_mode === 'flex' && slide.layout_tree != null

  useEffect(() => {
    return registerSlideSaveHandlers(slide.id, {
      commitFlex,
      commitCreateBlock,
      commitDeleteBlock,
      commitMutate,
      undo,
    })
  }, [
    slide.id,
    commitFlex,
    commitCreateBlock,
    commitDeleteBlock,
    commitMutate,
    undo,
  ])
  const articleRef = useRef<HTMLElement | null>(null)
  const [blockEl, setBlockEl] = useState<HTMLElement | null>(null)
  const [flexPreview, setFlexPreview] = useState<FlexContainer | null>(null)
  const [flexDragging, setFlexDragging] = useState(false)
  const selectedBlock =
    selectedBlockId != null
      ? (slide.blocks.find((block) => block.id === selectedBlockId) ?? null)
      : null
  const renderSlide: Slide = flexPreview
    ? ({ ...toRenderSlide(slide), layout_tree: flexPreview } as Slide)
    : toRenderSlide(slide)
  const overflowSlotIds = new Set(
    slide.issues
      .filter(
        (issue) =>
          issue.code === 'overflow' ||
          issue.message.includes('溢出') ||
          issue.message.includes('超出画布'),
      )
      .flatMap((issue) => (issue.slot_id ? [issue.slot_id] : ['*'])),
  )

  useEffect(() => {
    setFlexPreview(null)
  }, [slide.id, slide.revision])

  useEffect(() => {
    if (!selectedBlockId || !articleRef.current) {
      setBlockEl(null)
      return
    }
    const node = articleRef.current.querySelector<HTMLElement>(
      `[data-block-id="${CSS.escape(selectedBlockId)}"]`,
    )
    setBlockEl(node)
  }, [selectedBlockId, slide.blocks, zoom, flexPreview])

  // 仅当前可视页响应撤销/重做，避免多页 SlidePage 抢同一快捷键
  useEffect(() => {
    if (!active || !editable) return

    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      const editingText =
        target?.isContentEditable ||
        target?.closest('[contenteditable="true"]') != null ||
        target?.tagName === 'INPUT' ||
        target?.tagName === 'TEXTAREA'

      if (
        isFlex &&
        selectedBlockId &&
        !editingText &&
        (event.key === 'Delete' || event.key === 'Backspace') &&
        !event.metaKey &&
        !event.ctrlKey &&
        !event.altKey
      ) {
        event.preventDefault()
        commitDeleteBlock(selectedBlockId)
        onSelectBlock(null)
        return
      }

      const mod = event.metaKey || event.ctrlKey
      if (!mod) return
      const key = event.key.toLowerCase()
      const isUndo = key === 'z' && !event.shiftKey
      const isRedo = (key === 'z' && event.shiftKey) || key === 'y'
      if (!isUndo && !isRedo) return

      // 系统输入框（若有）不拦截；画布 contenteditable 的未提交草稿由 EditableText 处理
      if (
        target &&
        (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') &&
        !target.closest('[data-slide-id]')
      ) {
        return
      }

      if (isUndo) {
        if (!canUndo) return
        event.preventDefault()
        undo()
        return
      }
      if (!canRedo) return
      event.preventDefault()
      redo()
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [
    active,
    editable,
    canUndo,
    canRedo,
    undo,
    redo,
    historyTick,
    isFlex,
    selectedBlockId,
    commitDeleteBlock,
    onSelectBlock,
  ])

  return (
    <article
      ref={(node) => {
        articleRef.current = node
        bindEl(slide.id, node)
      }}
      data-slide-id={slide.id}
      aria-current={active ? 'true' : undefined}
      className="relative flex w-full flex-col items-center gap-2"
    >
      <div className="flex w-full max-w-[76rem] items-center gap-2 px-1">
        <span
          className={cn(
            'text-[11px] font-medium tabular-nums',
            active ? 'text-accent' : 'text-ink-muted',
          )}
        >
          {index + 1} / {total}
        </span>
        <span className="truncate text-[11px] text-ink-muted">{slide.title}</span>
        <SaveIndicator status={status} error={error} onRefresh={refresh} />
        {active && isFlex && editable && (
          <button
            type="button"
            onClick={onOpenRelayout}
            className="ml-auto inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-medium text-ink-soft transition-colors hover:bg-surface-soft hover:text-ink"
          >
            <RefreshCw className="size-3" />
            换排布
          </button>
        )}
      </div>

      {slide.status === 'ready' ? (
        <div
          style={{ width: `${zoom * 100}%`, maxWidth: zoom <= 1 ? '76rem' : 'none' }}
          className={cn(
            'relative shrink-0 shadow-slide transition-[box-shadow,outline-color]',
            active ? 'outline-2 outline-accent/35 outline-offset-4' : 'outline-none',
          )}
        >
          <div className={cn('relative', editable ? 'overflow-visible' : 'overflow-hidden')}>
            <SlideView
              slide={renderSlide}
              theme={theme}
              slideIndex={index}
              editable={editable}
              selectedBlockId={selectedBlockId}
              onSelectBlock={onSelectBlock}
              onCommit={commit}
              overflowMode={editable ? 'reveal' : 'clip'}
              overflowSlotIds={overflowSlotIds}
            />
            {isFlex && editable && (
              <FlexEditLayer
                projectId={projectId}
                slide={slide}
                tree={slide.layout_tree as FlexContainer}
                selectedBlockId={selectedBlockId}
                busy={status === 'saving'}
                onPreviewTree={setFlexPreview}
                onCommitTree={commitFlex}
                onSelectBlock={(blockId) => onSelectBlock(blockId)}
                onDraggingChange={setFlexDragging}
              />
            )}
          </div>
        </div>
      ) : (
        <div
          style={{ width: `${zoom * 100}%`, maxWidth: zoom <= 1 ? '76rem' : 'none' }}
          className="grid min-h-56 place-items-center"
        >
          <PendingStage
            slide={slide}
            disabled={locked || retry.isPending}
            onRetry={() => retry.mutate(slide.id)}
          />
        </div>
      )}

      {editable &&
        selectedBlock &&
        selectedBlock.type !== 'chart' &&
        !flexDragging && (
        <ElementToolbar
          articleEl={articleRef.current}
          blockEl={blockEl}
          block={selectedBlock}
          theme={theme}
          disabled={status === 'saving'}
          onChange={(style: BlockStyle | null) => commitStyle(selectedBlock.id, style)}
          onCommitContent={(change) => commit(selectedBlock.id, change)}
          flexPreset={
            isFlex && slide.layout_tree != null
              ? (findLeafParent(slide.layout_tree as FlexContainer, selectedBlock.id)
                  ?.parent.preset ?? null)
              : null
          }
          onFlexPresetChange={
            isFlex && slide.layout_tree != null
              ? (preset) => {
                  const tree = slide.layout_tree as FlexContainer
                  const found = findLeafParent(tree, selectedBlock.id)
                  if (!found) return
                  const next = setContainerPreset(tree, found.parent.id, preset)
                  if (!next) return
                  commitFlex(next)
                }
              : undefined
          }
          onDelete={
            isFlex
              ? () => {
                  commitDeleteBlock(selectedBlock.id)
                  onSelectBlock(null)
                }
              : undefined
          }
          onDismiss={() => onSelectBlock(null)}
        />
      )}
      {editable &&
        selectedBlock?.type === 'chart' &&
        !flexDragging && (
          <ChartDataEditor
            articleEl={articleRef.current}
            blockEl={blockEl}
            block={selectedBlock}
            disabled={status === 'saving'}
            onCommit={(change) => commit(selectedBlock.id, change)}
            onDismiss={() => onSelectBlock(null)}
          />
        )}
    </article>
  )
}

function PendingStage({
  slide,
  disabled,
  onRetry,
}: {
  slide: DeckSlide
  disabled: boolean
  onRetry: () => void
}) {
  if (slide.status === 'failed') {
    return (
      <div className="max-w-sm rounded-3xl border border-line bg-surface px-8 py-10 text-center shadow-card">
        <AlertTriangle className="mx-auto mb-3 size-5 text-negative" />
        <p className="text-sm font-medium">这一页没有生成成功</p>
        <p className="mt-1.5 text-[13px] leading-relaxed text-ink-muted">
          {slide.error ?? '可以直接重试，其他页面不受影响。'}
        </p>
        <Button className="mt-5" size="sm" disabled={disabled} onClick={onRetry}>
          <RotateCw className="size-3.5" />
          重试这一页
        </Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center gap-3 text-ink-muted">
      <Loader2 className="size-5 animate-spin" />
      <p className="text-[13px]">正在生成这一页…</p>
    </div>
  )
}

function SaveIndicator({
  status,
  error,
  onRefresh,
}: {
  status: SaveStatus
  error: string | null
  onRefresh: () => void
}) {
  if (status === 'idle') return null

  if (status === 'saving') {
    return <span className="ml-auto text-xs text-ink-muted">保存中…</span>
  }
  if (status === 'saved') {
    return <span className="ml-auto text-xs text-positive">已保存</span>
  }
  if (status === 'conflict') {
    return (
      <span className="ml-auto flex items-center gap-2 text-xs text-negative">
        {error ?? '页面已被其他操作更新'}
        <button
          type="button"
          onClick={onRefresh}
          className="text-ink-muted underline-offset-2 hover:text-accent hover:underline"
        >
          刷新
        </button>
      </span>
    )
  }
  return (
    <span role="alert" className="ml-auto text-xs text-negative">
      {error ?? '保存失败'}
    </span>
  )
}
