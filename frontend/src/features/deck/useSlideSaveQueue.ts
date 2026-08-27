import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '@/api/client'
import {
  commitSlideToCache,
  createSlideBlock,
  deckKey,
  deleteSlideBlock,
  updateFlexLayout,
  updateFlexState,
  updateSlideBlock,
  updateSlideBlockStyle,
} from '@/features/deck/api'
import {
  applyContentBody,
  contentBodyFromBlock,
  sameContent,
  sameStyle,
  styleFromBlock,
} from '@/features/deck/blockSnapshot'
import { normalizeGrows } from '@/features/deck/flexNormalize'
import type { FlexBlockType } from '@/features/deck/flexTree'
import { mergeBlockCommit, sanitizeBulletsItems } from '@/features/deck/mergeBlockCommit'
import type { BlockUpdateBody, Deck, DeckSlide } from '@/features/deck/types'
import { errorMessage } from '@/lib/errors'
import type { BlockStyle } from '@/render/blockStyle'
import type { FlexContainer } from '@/render/flexLayout'
import type { EditableBlockCommit } from '@/render/types'

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'conflict' | 'error'

export type StructureSnap = {
  blocks: DeckSlide['blocks']
  layout_tree: FlexContainer
}

type PendingJob =
  | { kind: 'content'; blockId: string; body: BlockUpdateBody }
  | { kind: 'style'; blockId: string; style: BlockStyle | null }
  | { kind: 'flex'; tree: FlexContainer; before: StructureSnap | null }
  | { kind: 'structure'; state: StructureSnap }
  | {
      kind: 'mutate'
      run: (slide: DeckSlide) => Promise<DeckSlide>
      record: boolean
    }

type HistoryEntry =
  | {
      kind: 'content'
      blockId: string
      before: BlockUpdateBody
      after: BlockUpdateBody
    }
  | {
      kind: 'style'
      blockId: string
      before: BlockStyle | null
      after: BlockStyle | null
    }
  | {
      kind: 'structure'
      before: StructureSnap
      after: StructureSnap
    }

const MAX_HISTORY = 50

function cloneSnap(snap: StructureSnap): StructureSnap {
  return {
    blocks: structuredClone(snap.blocks),
    layout_tree: structuredClone(snap.layout_tree),
  }
}

function structureSnap(slide: DeckSlide): StructureSnap | null {
  if (slide.layout_mode !== 'flex' || slide.layout_tree == null) return null
  return {
    blocks: structuredClone(slide.blocks),
    layout_tree: structuredClone(slide.layout_tree as FlexContainer),
  }
}

function sameStructure(a: StructureSnap, b: StructureSnap): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

/**
 * 同一页的块保存必须串行：每次成功 revision +1，并发必然 409。
 * 内容、样式、灵活布局结构共用队列；同时维护本页撤销/重做栈。
 */
export function useSlideSaveQueue(projectId: string, slideId: string) {
  const queryClient = useQueryClient()
  const queueRef = useRef<PendingJob[]>([])
  const runningRef = useRef(false)
  const contentOverridesRef = useRef(new Map<string, BlockUpdateBody>())
  const styleOverridesRef = useRef(new Map<string, BlockStyle | null>())
  const undoStackRef = useRef<HistoryEntry[]>([])
  const redoStackRef = useRef<HistoryEntry[]>([])
  const applyingHistoryRef = useRef(false)
  const [status, setStatus] = useState<SaveStatus>('idle')
  const [error, setError] = useState<string | null>(null)
  const [historyTick, setHistoryTick] = useState(0)
  const savedTimerRef = useRef<number | null>(null)

  useEffect(
    () => () => {
      if (savedTimerRef.current != null) window.clearTimeout(savedTimerRef.current)
    },
    [],
  )

  // 换页时清空历史：撤销栈按页隔离
  useEffect(() => {
    undoStackRef.current = []
    redoStackRef.current = []
    setHistoryTick((n) => n + 1)
  }, [slideId])

  const readSlide = useCallback((): DeckSlide | undefined => {
    const deck = queryClient.getQueryData<Deck>(deckKey(projectId))
    return deck?.slides.find((slide) => slide.id === slideId)
  }, [projectId, queryClient, slideId])

  const bumpHistory = () => setHistoryTick((n) => n + 1)

  const pushHistory = (entry: HistoryEntry) => {
    if (applyingHistoryRef.current) return
    undoStackRef.current = [...undoStackRef.current.slice(-(MAX_HISTORY - 1)), entry]
    redoStackRef.current = []
    bumpHistory()
  }

  const paintBlock = useCallback(
    (blockId: string, recipe: (block: DeckSlide['blocks'][number]) => DeckSlide['blocks'][number]) => {
      queryClient.setQueryData<Deck>(deckKey(projectId), (current) => {
        if (!current) return current
        return {
          ...current,
          slides: current.slides.map((slide) => {
            if (slide.id !== slideId) return slide
            return {
              ...slide,
              blocks: slide.blocks.map((block) =>
                block.id === blockId ? recipe(block) : block,
              ),
            }
          }),
        }
      })
    },
    [projectId, queryClient, slideId],
  )

  const paintStructure = useCallback(
    (state: StructureSnap) => {
      queryClient.setQueryData<Deck>(deckKey(projectId), (current) => {
        if (!current) return current
        return {
          ...current,
          slides: current.slides.map((slide) => {
            if (slide.id !== slideId) return slide
            return {
              ...slide,
              layout_mode: 'flex' as const,
              blocks: state.blocks,
              layout_tree: state.layout_tree,
            }
          }),
        }
      })
    },
    [projectId, queryClient, slideId],
  )

  const paintTree = useCallback(
    (tree: FlexContainer) => {
      queryClient.setQueryData<Deck>(deckKey(projectId), (current) => {
        if (!current) return current
        return {
          ...current,
          slides: current.slides.map((slide) => {
            if (slide.id !== slideId) return slide
            return { ...slide, layout_tree: tree }
          }),
        }
      })
    },
    [projectId, queryClient, slideId],
  )

  const enqueue = (job: PendingJob) => {
    if (job.kind === 'content' || job.kind === 'style') {
      const existing = queueRef.current.findIndex(
        (item) => item.kind === job.kind && item.blockId === job.blockId,
      )
      if (existing >= 0) queueRef.current[existing] = job
      else queueRef.current.push(job)
      return
    }
    queueRef.current.push(job)
  }

  const markSaved = () => {
    if (savedTimerRef.current != null) window.clearTimeout(savedTimerRef.current)
    setStatus('saved')
    savedTimerRef.current = window.setTimeout(() => {
      setStatus((current) => (current === 'saved' ? 'idle' : current))
      savedTimerRef.current = null
    }, 1600)
  }

  const pump = useCallback(async () => {
    if (runningRef.current) return
    runningRef.current = true

    while (queueRef.current.length > 0) {
      const job = queueRef.current.shift()
      if (!job) break

      const slide = readSlide()
      if (!slide) continue

      setStatus('saving')
      setError(null)

      try {
        let updated: DeckSlide
        if (job.kind === 'content') {
          const raw = contentOverridesRef.current.get(job.blockId) ?? job.body
          const body =
            raw.type === 'bullets'
              ? { ...raw, items: sanitizeBulletsItems(raw.items) }
              : raw
          updated = await updateSlideBlock(projectId, slideId, job.blockId, {
            ...body,
            revision: slide.revision,
          })
          if (
            !queueRef.current.some(
              (item) => item.kind === 'content' && item.blockId === job.blockId,
            )
          ) {
            contentOverridesRef.current.delete(job.blockId)
          }
        } else if (job.kind === 'style') {
          const style = styleOverridesRef.current.has(job.blockId)
            ? styleOverridesRef.current.get(job.blockId)!
            : job.style
          updated = await updateSlideBlockStyle(projectId, slideId, job.blockId, {
            revision: slide.revision,
            style,
          })
          if (
            !queueRef.current.some(
              (item) => item.kind === 'style' && item.blockId === job.blockId,
            )
          ) {
            styleOverridesRef.current.delete(job.blockId)
          }
        } else if (job.kind === 'flex') {
          updated = await updateFlexLayout(projectId, slideId, {
            revision: slide.revision,
            layout_tree: job.tree,
          })
          const after = structureSnap(updated)
          if (
            job.before &&
            after &&
            !sameStructure(job.before, after) &&
            !applyingHistoryRef.current
          ) {
            pushHistory({ kind: 'structure', before: job.before, after })
          }
        } else if (job.kind === 'structure') {
          updated = await updateFlexState(projectId, slideId, {
            revision: slide.revision,
            blocks: job.state.blocks,
            layout_tree: job.state.layout_tree,
          })
        } else {
          const before = job.record ? structureSnap(slide) : null
          updated = await job.run(slide)
          const after = structureSnap(updated)
          if (before && after && !sameStructure(before, after) && !applyingHistoryRef.current) {
            pushHistory({ kind: 'structure', before, after })
          }
        }

        commitSlideToCache(queryClient, projectId, updated)
        markSaved()
      } catch (cause) {
        const message = errorMessage(cause instanceof Error ? cause : null)
        const conflict =
          cause instanceof ApiError &&
          cause.status === 409 &&
          message.includes('其他操作更新')
        setStatus(conflict ? 'conflict' : 'error')
        setError(conflict ? '页面已被其他操作更新' : message)
        if (conflict) {
          queueRef.current = []
          break
        }
      }
    }

    runningRef.current = false
  }, [projectId, queryClient, readSlide, slideId])

  const applyContent = useCallback(
    (blockId: string, body: BlockUpdateBody, record: boolean) => {
      const slide = readSlide()
      const block = slide?.blocks.find((item) => item.id === blockId)
      if (block && record) {
        const before =
          contentOverridesRef.current.get(blockId) ?? contentBodyFromBlock(block)
        if (before && !sameContent(before, body)) {
          pushHistory({ kind: 'content', blockId, before, after: body })
        }
      }

      contentOverridesRef.current.set(blockId, body)
      paintBlock(blockId, (current) => applyContentBody(current, body))
      enqueue({ kind: 'content', blockId, body })
      void pump()
    },
    [paintBlock, pump, readSlide],
  )

  const applyStyle = useCallback(
    (blockId: string, style: BlockStyle | null, record: boolean) => {
      const slide = readSlide()
      const block = slide?.blocks.find((item) => item.id === blockId)
      if (block && record) {
        const before = styleOverridesRef.current.has(blockId)
          ? styleOverridesRef.current.get(blockId)!
          : styleFromBlock(block)
        if (!sameStyle(before, style)) {
          pushHistory({ kind: 'style', blockId, before, after: style })
        }
      }

      styleOverridesRef.current.set(blockId, style)
      paintBlock(blockId, (current) => ({ ...current, style }))
      enqueue({ kind: 'style', blockId, style })
      void pump()
    },
    [paintBlock, pump, readSlide],
  )

  const commit = useCallback(
    (blockId: string, change: EditableBlockCommit) => {
      if (change.type === 'style') {
        applyStyle(blockId, change.style, true)
        return
      }

      const slide = readSlide()
      if (!slide) return
      const body = mergeBlockCommit(
        slide,
        blockId,
        change,
        contentOverridesRef.current.get(blockId),
      )
      if (!body) return
      applyContent(blockId, body, true)
    },
    [applyContent, applyStyle, readSlide],
  )

  const commitStyle = useCallback(
    (blockId: string, style: BlockStyle | null) => {
      applyStyle(blockId, style, true)
    },
    [applyStyle],
  )

  const commitFlex = useCallback(
    (layout_tree: FlexContainer) => {
      const slide = readSlide()
      if (!slide || slide.layout_mode !== 'flex') return
      // 先按后端同款规则归一：否则乐观渲染的是草稿，响应回来又跳一次
      const tree = normalizeGrows(layout_tree)
      // 必须在 paint 前快照，否则 pump 里 before≈after，撤销栈进不去
      const before = structureSnap(slide)
      paintTree(tree)
      enqueue({ kind: 'flex', tree, before })
      void pump()
    },
    [paintTree, pump, readSlide],
  )

  const commitCreateBlock = useCallback(
    (body: { type: FlexBlockType; parent_id: string; index?: number }) => {
      enqueue({
        kind: 'mutate',
        record: true,
        run: (current) =>
          createSlideBlock(projectId, slideId, {
            revision: current.revision,
            type: body.type,
            parent_id: body.parent_id,
            index: body.index ?? 0,
          }),
      })
      void pump()
    },
    [projectId, pump, slideId],
  )

  const commitDeleteBlock = useCallback(
    (blockId: string) => {
      enqueue({
        kind: 'mutate',
        record: true,
        run: (current) =>
          deleteSlideBlock(projectId, slideId, blockId, { revision: current.revision }),
      })
      void pump()
    },
    [projectId, pump, slideId],
  )

  /** 多步结构变更（如插入多列）串行执行并记一条撤销 */
  const commitMutate = useCallback(
    (run: (slide: DeckSlide) => Promise<DeckSlide>) => {
      enqueue({ kind: 'mutate', record: true, run })
      void pump()
    },
    [pump],
  )

  const applyEntry = useCallback(
    (entry: HistoryEntry, side: 'before' | 'after') => {
      applyingHistoryRef.current = true
      try {
        if (entry.kind === 'content') {
          applyContent(entry.blockId, entry[side], false)
        } else if (entry.kind === 'style') {
          applyStyle(entry.blockId, entry[side], false)
        } else {
          const state = cloneSnap(entry[side])
          paintStructure(state)
          enqueue({ kind: 'structure', state })
          void pump()
        }
      } finally {
        applyingHistoryRef.current = false
      }
    },
    [applyContent, applyStyle, paintStructure, pump],
  )

  const undo = useCallback((): boolean => {
    const entry = undoStackRef.current.pop()
    if (!entry) return false
    redoStackRef.current.push(entry)
    bumpHistory()
    applyEntry(entry, 'before')
    return true
  }, [applyEntry])

  const redo = useCallback((): boolean => {
    const entry = redoStackRef.current.pop()
    if (!entry) return false
    undoStackRef.current.push(entry)
    bumpHistory()
    applyEntry(entry, 'after')
    return true
  }, [applyEntry])

  const refresh = useCallback(() => {
    contentOverridesRef.current.clear()
    styleOverridesRef.current.clear()
    queueRef.current = []
    undoStackRef.current = []
    redoStackRef.current = []
    setError(null)
    setStatus('idle')
    bumpHistory()
    void queryClient.invalidateQueries({ queryKey: deckKey(projectId) })
  }, [projectId, queryClient])

  return {
    commit,
    commitStyle,
    commitFlex,
    commitCreateBlock,
    commitDeleteBlock,
    commitMutate,
    undo,
    redo,
    canUndo: undoStackRef.current.length > 0,
    canRedo: redoStackRef.current.length > 0,
    historyTick,
    status,
    error,
    refresh,
  }
}
