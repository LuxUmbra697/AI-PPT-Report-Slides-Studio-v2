import { AlertTriangle, Loader2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { WorkbenchHeader } from '@/components/WorkbenchHeader'
import { Button } from '@/components/ui/Button'
import {
  useCancelDeck,
  useDeck,
  useDeleteSlide,
  useDuplicateSlide,
  useGenerateDeck,
  useInsertSlide,
  useReorderSlides,
} from '@/features/deck/api'
import { DeleteSlideDialog } from '@/features/deck/DeleteSlideDialog'
import { EditorHeaderActions } from '@/features/deck/EditorHeaderActions'
import { EditorRail } from '@/features/deck/EditorRail'
import type { BlockSelection, RailTab } from '@/features/deck/editorTypes'
import { ZOOM_STEPS } from '@/features/deck/editorTypes'
import { EmptyStage } from '@/features/deck/EmptyStage'
import { ExportDialog } from '@/features/deck/ExportDialog'
import { Filmstrip } from '@/features/deck/Filmstrip'
import { PresentMode } from '@/features/deck/PresentMode'
import { RelayoutDock } from '@/features/deck/RelayoutPanel'
import { SlideStage } from '@/features/deck/SlideStage'
import { useDeckProgress } from '@/features/deck/useDeckProgress'
import type { ProjectDetail } from '@/features/projects/types'
import { errorMessage } from '@/lib/errors'
import { resolveTheme, type ThemeOverrides } from '@/render/themeOverrides'

/**
 * 编辑工作台：生成中就能进来，完成一页看一页。
 * 所有高频动作（改文字、切页、AI、演示、导出）都不离开这一屏。
 */
export function EditorWorkspace({ project }: { project: ProjectDetail }) {
  const deckQuery = useDeck(project.id)
  const deck = deckQuery.data
  const slides = deck?.slides ?? []
  // deck.status 是主信号；project.status 只覆盖「已入队但页仍 pending / 页间空隙」。
  // deck 已 ready 时不再信过期的 project.generating，避免顶栏卡在「取消生成」。
  const generating =
    deck?.status === 'generating' ||
    (project.status === 'generating' &&
      (deck == null ||
        (deck.status !== 'ready' &&
          deck.slides.some(
            (slide) => slide.status === 'pending' || slide.status === 'generating',
          ))))
  const progress = useDeckProgress(project.id, generating)
  const theme = resolveTheme(
    project.theme_id,
    (project.theme_overrides ?? {}) as ThemeOverrides,
  )

  const generate = useGenerateDeck(project.id)
  const cancel = useCancelDeck(project.id)
  const reorder = useReorderSlides(project.id)
  const insertSlide = useInsertSlide(project.id)
  const duplicateSlide = useDuplicateSlide(project.id)
  const deleteSlide = useDeleteSlide(project.id)

  const [activeId, setActiveId] = useState<string | null>(null)
  const [scrollRequest, setScrollRequest] = useState<{ id: string; nonce: number } | null>(null)
  const [selection, setSelection] = useState<BlockSelection | null>(null)
  const [rail, setRail] = useState<RailTab | null>(null)
  const [relayoutOpen, setRelayoutOpen] = useState(false)
  const [zoomIndex, setZoomIndex] = useState(1)
  const [presenting, setPresenting] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [removingId, setRemovingId] = useState<string | null>(null)

  // 用 id 串做依赖：deck 每次轮询都会换掉数组身份，但选中页不该因此跳走
  const slideIdsKey = slides.map((slide) => slide.id).join('|')
  // 块增删 / AI 改结构时页 id 不变，需按页单独跟踪 block id 集合。
  // 依赖 deck?.slides（而非 slides）：避免 `?? []` 每轮新引用触发无意义重算
  const blockIdsBySlide = useMemo(() => {
    const index = new Map<string, Set<string>>()
    for (const slide of deck?.slides ?? []) {
      index.set(
        slide.id,
        new Set(slide.blocks.map((block) => block.id)),
      )
    }
    return index
  }, [deck?.slides])
  useEffect(() => {
    const ids = slideIdsKey ? slideIdsKey.split('|') : []
    setActiveId((current) => (current && ids.includes(current) ? current : (ids[0] ?? null)))
  }, [slideIdsKey])

  useEffect(() => {
    setSelection((current) => {
      if (!current) return null
      // 选中的块可能已被删除或被 AI 改结构换掉，此时连页选中一并清空
      if (!blockIdsBySlide.get(current.slideId)?.has(current.blockId)) return null
      return current
    })
  }, [blockIdsBySlide])

  useEffect(() => {
    if (!activeId) return
    setSelection((current) =>
      current && current.slideId !== activeId ? null : current,
    )
  }, [activeId])

  useEffect(() => {
    setRelayoutOpen(false)
  }, [activeId])

  const focusSlide = (id: string) => {
    setActiveId(id)
    setScrollRequest({ id, nonce: Date.now() })
  }

  // 整页操作会重排页序，成功后跳到后端指定的那一页（新页，或删除后的邻页）
  const focusResult = (result: { slide_id?: string | null }) => {
    if (result.slide_id) focusSlide(result.slide_id)
  }

  const active = slides.find((slide) => slide.id === activeId) ?? null
  const removing = slides.find((slide) => slide.id === removingId) ?? null
  const pageBusy = insertSlide.isPending || duplicateSlide.isPending || deleteSlide.isPending
  const ready = progress.event?.ready ?? deck?.ready ?? 0
  const failed = progress.event?.failed ?? deck?.failed ?? 0
  const total = progress.event?.total ?? deck?.total ?? 0
  const actionError =
    generate.error ??
    cancel.error ??
    reorder.error ??
    insertSlide.error ??
    duplicateSlide.error ??
    deleteSlide.error

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <WorkbenchHeader
        title={project.title}
        meta={
          generating ? (
            <span className="flex shrink-0 items-center gap-1.5 rounded-full bg-accent-soft px-2.5 py-0.5 text-[11px] font-medium text-accent tabular-nums">
              <Loader2 className="size-3 animate-spin" />
              {ready} / {total} 页
            </span>
          ) : failed > 0 ? (
            <span className="flex shrink-0 items-center gap-1.5 rounded-full bg-negative/10 px-2.5 py-0.5 text-[11px] font-medium text-negative">
              <AlertTriangle className="size-3" />
              {failed} 页失败
            </span>
          ) : total > 0 ? (
            <span className="shrink-0 rounded-full bg-surface-soft px-2.5 py-0.5 text-[11px] font-medium text-ink-muted tabular-nums">
              {total} 页
            </span>
          ) : null
        }
      >
        {generating ? (
          <Button variant="ghost" size="sm" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
            {cancel.isPending ? '正在取消…' : '取消生成'}
          </Button>
        ) : (
          <EditorHeaderActions
            slides={slides}
            failed={failed}
            deckStatus={deck?.status}
            generatePending={generate.isPending}
            onContinueGenerate={() => generate.mutate({ regenerateAll: false })}
            onPresent={() => setPresenting(true)}
            onExport={() => setExporting(true)}
            onRegenerateAll={() => generate.mutate({ regenerateAll: true })}
          />
        )}
      </WorkbenchHeader>

      {actionError && (
        <p role="alert" className="bg-negative/8 px-5 py-2 text-[13px] text-negative">
          {errorMessage(actionError)}
        </p>
      )}

      <div className="flex min-h-0 flex-1">
        {slides.length > 0 && (
          <Filmstrip
            projectId={project.id}
            slides={slides}
            theme={theme}
            activeId={activeId}
            locked={generating}
            busy={pageBusy}
            onSelect={focusSlide}
            onReorder={reorder.mutate}
            onInsert={(afterSlideId) =>
              insertSlide.mutate(afterSlideId, { onSuccess: focusResult })
            }
            onDuplicate={(slideId) =>
              duplicateSlide.mutate(slideId, { onSuccess: focusResult })
            }
            onDelete={setRemovingId}
          />
        )}

        {slides.length === 0 ? (
          <EmptyStage
            pending={generate.isPending || deckQuery.isPending}
            onGenerate={() => generate.mutate({ regenerateAll: false })}
          />
        ) : (
          <SlideStage
            projectId={project.id}
            slides={slides}
            activeId={activeId}
            scrollRequest={scrollRequest}
            theme={theme}
            locked={generating}
            zoom={ZOOM_STEPS[zoomIndex]}
            canZoomOut={zoomIndex > 0}
            canZoomIn={zoomIndex < ZOOM_STEPS.length - 1}
            selection={selection}
            onSelectionChange={setSelection}
            onActiveChange={setActiveId}
            onOpenRelayout={() => {
              setRelayoutOpen(true)
              setRail(null)
            }}
            onZoom={(delta) =>
              setZoomIndex((current) =>
                Math.min(Math.max(current + delta, 0), ZOOM_STEPS.length - 1),
              )
            }
          />
        )}

        {active && relayoutOpen && active.layout_mode === 'flex' && (
          <RelayoutDock
            projectId={project.id}
            slide={active}
            theme={theme}
            open={relayoutOpen}
            disabled={generating || active.status !== 'ready'}
            onClose={() => setRelayoutOpen(false)}
          />
        )}

        {active && (
          <EditorRail
            project={project}
            slide={active}
            theme={theme}
            tab={rail}
            locked={generating}
            selectedBlockId={
              selection?.slideId === active.id ? selection.blockId : null
            }
            onTab={(next) => {
              setRelayoutOpen(false)
              setRail((current) => (current === next ? null : next))
            }}
            onOpenRelayout={() => {
              setRelayoutOpen(true)
              setRail(null)
            }}
          />
        )}
      </div>

      {presenting && (
        <PresentMode
          slides={slides.filter((slide) => slide.status === 'ready')}
          theme={theme}
          startIndex={Math.max(
            0,
            slides.filter((slide) => slide.status === 'ready').findIndex((slide) => slide.id === activeId),
          )}
          onClose={() => setPresenting(false)}
        />
      )}

      {exporting && deck && (
        <ExportDialog
          projectId={project.id}
          deck={deck}
          onClose={() => setExporting(false)}
          onLocate={focusSlide}
        />
      )}

      {removing && (
        <DeleteSlideDialog
          slide={removing}
          slideCount={slides.length}
          pending={deleteSlide.isPending}
          onClose={() => setRemovingId(null)}
          onConfirm={() =>
            deleteSlide.mutate(removing.id, {
              onSuccess: (result) => {
                setRemovingId(null)
                focusResult(result)
              },
            })
          }
        />
      )}
    </div>
  )
}
