import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import { insertColumnsAt } from '@/features/deck/BlockInsertRail'
import {
  activateCornerGrow,
  growStartT,
  ratioStartT,
  resolveDragTree,
  type DragSession,
  type ResizeDragSession,
} from '@/features/deck/flexEditDragSession'
import {
  AXIS_X_GATE_PX,
  movedPastThreshold,
  resolveAxisLock,
  resolveCornerAxisLock,
} from '@/features/deck/flexEditGeometry'
import { normalizeGrows } from '@/features/deck/flexNormalize'
import {
  collectColumnDividers,
  collectRowDividers,
  ensureResizePair,
  findContainerById,
  iterLeaves,
  leafOffset,
  moveLeaf,
  resolveDropTarget,
  resolveInsertAnchor,
  setLeafOffset,
  type ColumnDivider,
  type ResizePair,
  type ResizeSide,
  type RowDivider,
} from '@/features/deck/flexTree'
import {
  getSlideSaveHandlers,
  registerInsertDragStarter,
} from '@/features/deck/slideSaveBridge'
import type { DeckSlide } from '@/features/deck/types'
import { solve, solveNodeAreas, type FlexContainer, type FlexNode } from '@/render/flexLayout'

const BLOCK_LABEL: Record<string, string> = {
  text: '文本',
  bullets: '列表',
  image: '图片',
  kpi: 'KPI',
  cards: '卡片',
  callout: '提示',
  table: '表格',
  chart: '图表',
}

const NUDGE_DIRECTIONS: Record<string, [number, number]> = {
  ArrowLeft: [-1, 0],
  ArrowRight: [1, 0],
  ArrowUp: [0, -1],
  ArrowDown: [0, 1],
}

const NUDGE_STEP_PT = 1
const NUDGE_COARSE_STEP_PT = 10
/** 连续按键合并成一次保存与一条撤销记录 */
const NUDGE_FLUSH_MS = 260

function isTextEntryTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable) return true
  return ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
}

export function useFlexPointerSession({
  projectId,
  slide,
  tree,
  selectedBlockId,
  busy,
  onPreviewTree,
  onCommitTree,
  onSelectBlock,
  onDraggingChange,
}: {
  projectId: string
  slide: DeckSlide
  tree: FlexContainer
  selectedBlockId: string | null
  busy?: boolean
  onPreviewTree?: (next: FlexContainer | null) => void
  onCommitTree: (next: FlexContainer) => void
  onSelectBlock?: (blockId: string) => void
  onDraggingChange?: (dragging: boolean) => void
}) {
  const rootRef = useRef<HTMLDivElement>(null)
  const treeRef = useRef(tree)
  treeRef.current = tree
  const onCommitRef = useRef(onCommitTree)
  onCommitRef.current = onCommitTree
  const onPreviewRef = useRef(onPreviewTree)
  onPreviewRef.current = onPreviewTree
  const onDraggingRef = useRef(onDraggingChange)
  onDraggingRef.current = onDraggingChange
  const selectedBlockIdRef = useRef(selectedBlockId)
  selectedBlockIdRef.current = selectedBlockId
  const projectIdRef = useRef(projectId)
  projectIdRef.current = projectId
  const slideIdRef = useRef(slide.id)
  slideIdRef.current = slide.id
  const busyRef = useRef(busy)
  busyRef.current = busy

  const [drag, setDrag] = useState<DragSession | null>(null)
  const [previewTree, setPreviewTree] = useState<FlexContainer | null>(null)
  const [hoveredBlockId, setHoveredBlockId] = useState<string | null>(null)
  const [hoveredDividerKey, setHoveredDividerKey] = useState<string | null>(null)

  const dragRef = useRef<DragSession | null>(null)
  dragRef.current = drag
  // 只由 showPreview / clearPreview 维护，不在 render 里回写：否则拖拽中的
  // 其它 setState 会把 ref 退回上一帧，松手提交到旧树
  const previewRef = useRef<FlexContainer | null>(null)
  /** 已提交、正等新树回到 props：期间保住预览，避免中途落回旧树 */
  const awaitCommitRef = useRef(false)

  const showPreview = (next: FlexContainer) => {
    // 同步写 ref：松手读到的必须是最后一帧，否则提交的是上一帧的树
    previewRef.current = next
    setPreviewTree(next)
    onPreviewRef.current?.(next)
  }

  const clearPreview = () => {
    awaitCommitRef.current = false
    previewRef.current = null
    setPreviewTree(null)
    onPreviewRef.current?.(null)
  }

  useEffect(() => {
    if (!awaitCommitRef.current) return
    awaitCommitRef.current = false
    previewRef.current = null
    setPreviewTree(null)
    onPreviewRef.current?.(null)
  }, [tree])

  const activeTree = previewTree ?? tree
  const placements = useMemo(() => {
    const map = new Map<string, { x: number; y: number; w: number; h: number }>()
    for (const placed of solve(activeTree)) {
      map.set(placed.block_id, placed.rect)
    }
    return map
  }, [activeTree])

  const basePlacements = useMemo(() => {
    const map = new Map<string, { x: number; y: number; w: number; h: number }>()
    for (const placed of solve(tree)) {
      map.set(placed.block_id, placed.rect)
    }
    return map
  }, [tree])
  const basePlacementsRef = useRef(basePlacements)
  basePlacementsRef.current = basePlacements

  const rowDividers = useMemo(
    () => collectRowDividers(activeTree, placements),
    [activeTree, placements],
  )
  const columnDividers = useMemo(
    () => collectColumnDividers(activeTree, placements),
    [activeTree, placements],
  )

  const blockIds = useMemo(
    () => iterLeaves(tree).map((leaf) => leaf.block_id),
    [tree],
  )

  const dragging = drag != null
  const draggingBlockId = drag?.kind === 'reorder' ? drag.blockId : null

  useEffect(() => {
    onDraggingRef.current?.(dragging)
  }, [dragging])

  useEffect(() => {
    if (!draggingBlockId) return
    const host = rootRef.current?.parentElement
    if (!host) return
    const el = host.querySelector<HTMLElement>(
      `[data-block-id="${CSS.escape(draggingBlockId)}"]`,
    )
    if (!el) return
    const prev = el.style.opacity
    el.style.opacity = '0.15'
    return () => {
      el.style.opacity = prev
    }
  }, [draggingBlockId, previewTree])

  useEffect(() => {
    if (!dragging) return

    const toNorm = (clientX: number, clientY: number) => {
      const el = rootRef.current
      if (!el) return null
      const box = el.getBoundingClientRect()
      if (box.width <= 0 || box.height <= 0) return null
      return {
        x: (clientX - box.left) / box.width,
        y: (clientY - box.top) / box.height,
      }
    }

    const onMove = (event: PointerEvent) => {
      let session = dragRef.current
      if (!session) return
      const pointer = toNorm(event.clientX, event.clientY)
      if (!pointer) return
      const currentTree = treeRef.current

      if (session.kind === 'reorder' || session.kind === 'insert') {
        if (session.kind === 'insert' && !session.activated) {
          if (
            !movedPastThreshold(
              session.startClientX,
              session.startClientY,
              event.clientX,
              event.clientY,
            )
          ) {
            setDrag({
              ...session,
              pointerX: pointer.x,
              pointerY: pointer.y,
            })
            return
          }
          session = { ...session, activated: true }
        }
        const drop = resolveDropTarget({
          root: currentTree,
          placements: basePlacementsRef.current,
          pointer,
          draggedBlockId: session.kind === 'reorder' ? session.blockId : null,
          mode: session.kind,
        })
        setDrag({
          ...session,
          drop,
          pointerX: pointer.x,
          pointerY: pointer.y,
        })
        return
      }

      if (
        (session.kind === 'ratio' || session.kind === 'grow' || session.kind === 'box') &&
        session.deferPreview &&
        !session.activated
      ) {
        if (
          !movedPastThreshold(
            session.startClientX,
            session.startClientY,
            event.clientX,
            event.clientY,
          )
        ) {
          return
        }
        const dx = event.clientX - session.startClientX
        const dy = event.clientY - session.startClientY
        // 角点：按主轴决定是否补宽度拉伸对，避免纯纵向意图留下宽度包装
        let activated: ResizeDragSession
        if (session.kind === 'grow' && session.pendingCorner) {
          const adx = Math.abs(dx)
          const ady = Math.abs(dy)
          // 横向主导但未满门槛：继续等，避免 3px 激活后锁死成 Y 无法改宽
          if (adx > ady && adx < AXIS_X_GATE_PX) return
          activated = activateCornerGrow(session, resolveCornerAxisLock(dx, dy))
        } else if (session.kind === 'box') {
          activated = {
            ...session,
            activated: true,
            axisLock: resolveAxisLock(dx, dy),
          }
        } else {
          activated = { ...session, activated: true }
        }
        session = activated
        // 写穿 ref，避免连续 move 在 re-render 前重复激活、重算 lock
        dragRef.current = activated
        setDrag(activated)
        showPreview(normalizeGrows(activated.baseTree))
      }

      if (session.kind !== 'ratio' && session.kind !== 'grow' && session.kind !== 'box' && session.kind !== 'offset') {
        return
      }
      const next = resolveDragTree(session, pointer)
      if (next) showPreview(next)
    }

    /** 侧栏拖入：落点由 handlers 走服务端新建，本层没有可提交的树 */
    const runInsert = (session: Extract<DragSession, { kind: 'insert' }>) => {
      const handlers = getSlideSaveHandlers(slideIdRef.current)
      if (!handlers) return
      const anchor =
        session.activated && session.drop
          ? { parentId: session.drop.parentId, index: session.drop.index }
          : session.activated
            ? null
            : resolveInsertAnchor(treeRef.current, selectedBlockIdRef.current)
      if (!anchor) return
      const payload = session.payload
      if (payload.kind === 'block') {
        handlers.commitCreateBlock({
          type: payload.type,
          parent_id: anchor.parentId,
          index: anchor.index,
        })
        return
      }
      handlers.commitMutate((current) =>
        insertColumnsAt(projectIdRef.current, current, anchor, payload.count),
      )
    }

    /** 松手后要提交的新树；无需提交（未过阈值 / 无落点 / 插入）返回 null */
    const treeToCommit = (
      session: DragSession,
      draft: FlexContainer | null,
    ): FlexContainer | null => {
      if (session.kind === 'reorder') {
        if (!session.drop) return null
        return moveLeaf(
          treeRef.current,
          session.blockId,
          session.drop.parentId,
          session.drop.index,
        )
      }
      if (session.kind === 'insert') {
        runInsert(session)
        return null
      }
      if (session.kind !== 'offset' && session.deferPreview && !session.activated) {
        return null
      }
      return draft
    }

    const onUp = () => {
      const session = dragRef.current
      const draft = previewRef.current
      setDrag(null)
      const next = session ? treeToCommit(session, draft) : null
      if (!next) {
        clearPreview()
        return
      }
      // 预览留到提交后的新树到达再撤：立刻撤会先落回旧树，选中框闪一下
      awaitCommitRef.current = true
      onCommitRef.current(next)
    }

    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    window.addEventListener('pointercancel', onUp)
    return () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      window.removeEventListener('pointercancel', onUp)
    }
  }, [dragging])

  // 只读的悬停跟踪，保存中也继续，避免 busy 期间残留旧的悬停块
  useEffect(() => {
    const el = rootRef.current
    if (!el) return
    const parent = el.parentElement
    if (!parent) return

    const toNorm = (clientX: number, clientY: number) => {
      const box = el.getBoundingClientRect()
      if (box.width <= 0 || box.height <= 0) return null
      return {
        x: (clientX - box.left) / box.width,
        y: (clientY - box.top) / box.height,
      }
    }

    const onMove = (event: PointerEvent) => {
      if (dragRef.current) return
      const pointer = toNorm(event.clientX, event.clientY)
      if (!pointer) return
      let hit: string | null = null
      for (const [blockId, rect] of basePlacementsRef.current) {
        if (
          pointer.x >= rect.x &&
          pointer.x <= rect.x + rect.w &&
          pointer.y >= rect.y &&
          pointer.y <= rect.y + rect.h
        ) {
          hit = blockId
          break
        }
      }
      setHoveredBlockId(hit)
    }
    const onLeave = () => {
      if (!dragRef.current) setHoveredBlockId(null)
    }

    parent.addEventListener('pointermove', onMove)
    parent.addEventListener('pointerleave', onLeave)
    return () => {
      parent.removeEventListener('pointermove', onMove)
      parent.removeEventListener('pointerleave', onLeave)
    }
  }, [])

  // 方向键微调选中块位置：1pt，按住 Shift 为 10pt
  useEffect(() => {
    if (busy || !selectedBlockId) return

    let pending: FlexContainer | null = null
    let timer: number | null = null

    const flush = () => {
      timer = null
      const next = pending
      pending = null
      if (!next) return
      awaitCommitRef.current = true
      onCommitRef.current(next)
    }

    const onKeyDown = (event: KeyboardEvent) => {
      const direction = NUDGE_DIRECTIONS[event.key]
      if (!direction) return
      if (event.metaKey || event.ctrlKey || event.altKey) return
      if (isTextEntryTarget(event.target)) return
      event.preventDefault()

      const base = pending ?? treeRef.current
      const current = leafOffset(base, selectedBlockId)
      const step = event.shiftKey ? NUDGE_COARSE_STEP_PT : NUDGE_STEP_PT
      const next = setLeafOffset(
        base,
        selectedBlockId,
        current.x + direction[0] * step,
        current.y + direction[1] * step,
      )
      if (!next) return
      pending = next
      showPreview(next)
      if (timer != null) window.clearTimeout(timer)
      timer = window.setTimeout(flush, NUDGE_FLUSH_MS)
    }

    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      if (timer != null) window.clearTimeout(timer)
      flush()
    }
  }, [busy, selectedBlockId])

  const startReorder = (blockId: string, event: ReactPointerEvent) => {
    if (busy) return
    // 按住 Alt 改为像素级微调，不触发重排
    if (event.altKey) {
      startOffset(blockId, event)
      return
    }
    event.preventDefault()
    event.stopPropagation()
    onSelectBlock?.(blockId)

    const rect = basePlacements.get(blockId)
    const el = rootRef.current
    if (!rect || !el) {
      setDrag({
        kind: 'reorder',
        blockId,
        drop: null,
        grabOffsetX: 0.02,
        grabOffsetY: 0.02,
        ghostW: 0.2,
        ghostH: 0.12,
        pointerX: rect?.x ?? 0,
        pointerY: rect?.y ?? 0,
      })
      return
    }
    const box = el.getBoundingClientRect()
    const pointerX = (event.clientX - box.left) / box.width
    const pointerY = (event.clientY - box.top) / box.height
    setDrag({
      kind: 'reorder',
      blockId,
      drop: null,
      grabOffsetX: pointerX - rect.x,
      grabOffsetY: pointerY - rect.y,
      ghostW: rect.w,
      ghostH: rect.h,
      pointerX,
      pointerY,
    })
  }

  const measureRowSpan = (baseTree: FlexContainer, rowId: string) => {
    const row = findContainerById(baseTree, rowId)
    if (!row || row.type !== 'row') return null
    const areas = solveNodeAreas(baseTree)
    const rowArea = areas.get(rowId)
    if (rowArea && rowArea.w > 0) {
      return { rowX: rowArea.x, rowW: rowArea.w }
    }
    let x0 = Infinity
    let x1 = -Infinity
    for (const child of row.children) {
      for (const leaf of iterLeaves(child as FlexNode)) {
        const rect = solve(baseTree).find((p) => p.block_id === leaf.block_id)?.rect
        if (!rect) continue
        x0 = Math.min(x0, rect.x)
        x1 = Math.max(x1, rect.x + rect.w)
      }
    }
    if (!Number.isFinite(x0) || !Number.isFinite(x1) || x1 <= x0) return null
    return { rowX: x0, rowW: x1 - x0 }
  }

  const measureColSpan = (baseTree: FlexContainer, columnId: string) => {
    const areas = solveNodeAreas(baseTree)
    const colArea = areas.get(columnId)
    if (colArea && colArea.h > 0) {
      return { colY: colArea.y, colH: colArea.h }
    }
    return null
  }

  const startRatio = (
    divider: RowDivider,
    event: ReactPointerEvent,
    baseTree: FlexContainer = tree,
    opts?: { deferPreview?: boolean },
  ) => {
    if (busy) return
    event.preventDefault()
    event.stopPropagation()

    const span = measureRowSpan(baseTree, divider.rowId)
    if (!span) return
    const row = findContainerById(baseTree, divider.rowId)
    if (!row || row.type !== 'row') return
    const ratios =
      row.ratios?.length === row.children.length
        ? [...row.ratios]
        : Array.from({ length: row.children.length }, () => 100 / row.children.length)
    const el = rootRef.current
    if (!el) return
    const box = el.getBoundingClientRect()
    if (box.width <= 0) return
    const originX = (event.clientX - box.left) / box.width
    const deferPreview = Boolean(opts?.deferPreview)

    if (!deferPreview) showPreview(normalizeGrows(baseTree))
    setDrag({
      kind: 'ratio',
      rowId: divider.rowId,
      leftIndex: divider.leftIndex,
      rowX: span.rowX,
      rowW: span.rowW,
      baseTree,
      startT: ratioStartT(ratios, divider.leftIndex),
      originX,
      activated: !deferPreview,
      deferPreview,
      startClientX: event.clientX,
      startClientY: event.clientY,
    })
  }

  const startGrow = (
    divider: ColumnDivider,
    event: ReactPointerEvent,
    baseTree: FlexContainer = tree,
    opts?: { deferPreview?: boolean },
  ) => {
    if (busy) return
    event.preventDefault()
    event.stopPropagation()

    const span = measureColSpan(baseTree, divider.columnId)
    if (!span) return
    const column = findContainerById(baseTree, divider.columnId)
    if (!column || column.type !== 'column') return
    const grows = column.children.map((child) => child.grow ?? 1)
    const el = rootRef.current
    if (!el) return
    const box = el.getBoundingClientRect()
    if (box.height <= 0) return
    const originY = (event.clientY - box.top) / box.height
    const deferPreview = Boolean(opts?.deferPreview)

    if (!deferPreview) showPreview(normalizeGrows(baseTree))
    setDrag({
      kind: 'grow',
      columnId: divider.columnId,
      topIndex: divider.topIndex,
      colY: span.colY,
      colH: span.colH,
      baseTree,
      startT: growStartT(grows, divider.topIndex),
      originY,
      activated: !deferPreview,
      deferPreview,
      startClientX: event.clientX,
      startClientY: event.clientY,
    })
  }

  /** 选中块边手柄：先补占位块/包装，拖过阈值后再 preview */
  const beginBlockResize = (
    blockId: string,
    axis: 'x' | 'y',
    side: ResizeSide,
    event: ReactPointerEvent,
  ) => {
    if (busy) return
    const ensured = ensureResizePair(tree, blockId, axis, side)
    if (!ensured) return
    startFromPair(ensured, axis, event, { deferPreview: true })
  }

  const startFromPair = (
    pair: ResizePair,
    axis: 'x' | 'y',
    event: ReactPointerEvent,
    opts?: { deferPreview?: boolean },
  ) => {
    if (axis === 'x') {
      startRatio(
        { rowId: pair.containerId, leftIndex: pair.index, x: 0, y: 0, h: 0 },
        event,
        pair.tree,
        opts,
      )
      return
    }
    startGrow(
      { columnId: pair.containerId, topIndex: pair.index, x: 0, y: 0, w: 0 },
      event,
      pair.tree,
      opts,
    )
  }

  /**
   * 四角手柄：按下时只补纵向拉伸对；激活后按主轴决定是否补横向。
   * 避免「看起来在上下拉」却已包进宽度对、左右一晃就改宽。
   */
  const beginCornerResize = (
    blockId: string,
    sideX: ResizeSide,
    sideY: ResizeSide,
    event: ReactPointerEvent,
  ) => {
    if (busy) return
    const ensuredY = ensureResizePair(tree, blockId, 'y', sideY)
    if (!ensuredY) {
      beginBlockResize(blockId, 'x', sideX, event)
      return
    }
    const span = measureColSpan(ensuredY.tree, ensuredY.containerId)
    const column = findContainerById(ensuredY.tree, ensuredY.containerId)
    if (!span || !column || column.type !== 'column') {
      beginBlockResize(blockId, 'x', sideX, event)
      return
    }
    const el = rootRef.current
    if (!el) return
    const box = el.getBoundingClientRect()
    if (box.width <= 0 || box.height <= 0) return

    event.preventDefault()
    event.stopPropagation()
    const grows = column.children.map((child) => child.grow ?? 1)
    const originX = (event.clientX - box.left) / box.width
    const originY = (event.clientY - box.top) / box.height
    setDrag({
      kind: 'grow',
      columnId: ensuredY.containerId,
      topIndex: ensuredY.index,
      colY: span.colY,
      colH: span.colH,
      baseTree: ensuredY.tree,
      startT: growStartT(grows, ensuredY.index),
      originY,
      pendingCorner: { blockId, sideX, originX },
      activated: false,
      deferPreview: true,
      startClientX: event.clientX,
      startClientY: event.clientY,
    })
  }

  /** Alt + 拖动块体：像素级平移，不参与重排 */
  const startOffset = (blockId: string, event: ReactPointerEvent) => {
    const el = rootRef.current
    if (busy || !el) return
    const box = el.getBoundingClientRect()
    if (box.width <= 0 || box.height <= 0) return
    event.preventDefault()
    event.stopPropagation()
    onSelectBlock?.(blockId)

    const base = leafOffset(tree, blockId)
    showPreview(tree)
    setDrag({
      kind: 'offset',
      blockId,
      baseTree: tree,
      baseX: base.x,
      baseY: base.y,
      startX: (event.clientX - box.left) / box.width,
      startY: (event.clientY - box.top) / box.height,
    })
  }

  useEffect(() => {
    return registerInsertDragStarter(slide.id, (payload, clientX, clientY) => {
      if (busyRef.current) return
      const el = rootRef.current
      if (!el) return
      const box = el.getBoundingClientRect()
      if (box.width <= 0 || box.height <= 0) return
      const pointerX = (clientX - box.left) / box.width
      const pointerY = (clientY - box.top) / box.height
      setDrag({
        kind: 'insert',
        payload,
        drop: null,
        grabOffsetX: 0.06,
        grabOffsetY: 0.04,
        ghostW: 0.2,
        ghostH: 0.12,
        pointerX,
        pointerY,
        activated: false,
        startClientX: clientX,
        startClientY: clientY,
      })
    })
  }, [slide.id])

  const visibleHandleId = draggingBlockId ?? selectedBlockId ?? hoveredBlockId

  const ghostLabel = (() => {
    if (drag?.kind === 'insert') {
      if (drag.payload.kind === 'columns') return `${drag.payload.count} 列`
      return BLOCK_LABEL[drag.payload.type] ?? '内容块'
    }
    if (!draggingBlockId) return ''
    const block = slide.blocks.find((item) => item.id === draggingBlockId)
    if (!block) return '内容块'
    if (block.type === 'text') {
      const text = block.text.trim()
      return text ? text.slice(0, 24) : '文本'
    }
    if (block.type === 'bullets') {
      return block.items[0]?.trim() || '列表'
    }
    if (block.type === 'kpi') return block.value || 'KPI'
    return BLOCK_LABEL[block.type] ?? '内容块'
  })()

  const selectedRect =
    selectedBlockId != null ? placements.get(selectedBlockId) : null
  /** 保存中手柄照常画，只是不吃指针，位置因此不会闪断 */
  const hitClass = busy ? 'pointer-events-none' : 'pointer-events-auto'

  return {
    rootRef,
    drag,
    hoveredDividerKey,
    setHoveredDividerKey,
    rowDividers,
    columnDividers,
    blockIds,
    placements,
    dragging,
    draggingBlockId,
    visibleHandleId,
    selectedRect,
    hitClass,
    ghostLabel,
    startReorder,
    startRatio,
    startGrow,
    beginBlockResize,
    beginCornerResize,
  }
}
