import {
  BarChart3,
  Columns2,
  Columns3,
  Hash,
  Image as ImageIcon,
  LayoutGrid,
  List,
  MessageSquare,
  Table2,
  Type,
} from 'lucide-react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import {
  createSlideBlock,
  updateFlexLayout,
} from '@/features/deck/api'
import {
  type FlexBlockType,
  findContainerById,
  resolveInsertAnchor,
  wrapBlockIdsAsColumns,
} from '@/features/deck/flexTree'
import {
  getSlideSaveHandlers,
  requestInsertDrag,
} from '@/features/deck/slideSaveBridge'
import type { DeckSlide } from '@/features/deck/types'
import { cn } from '@/lib/utils'
import type { FlexContainer } from '@/render/flexLayout'

const BLOCK_BUTTONS: Array<{
  type: FlexBlockType
  label: string
  icon: typeof Type
}> = [
  { type: 'text', label: '文本', icon: Type },
  { type: 'bullets', label: '列表', icon: List },
  { type: 'image', label: '图片', icon: ImageIcon },
  { type: 'kpi', label: 'KPI', icon: Hash },
  { type: 'cards', label: '卡片', icon: LayoutGrid },
  { type: 'callout', label: '提示', icon: MessageSquare },
  { type: 'table', label: '表格', icon: Table2 },
  { type: 'chart', label: '图表', icon: BarChart3 },
]

export type InsertAnchor = { parentId: string; index: number }

export async function insertColumnsAt(
  projectId: string,
  slide: DeckSlide,
  anchor: InsertAnchor,
  count: 2 | 3,
): Promise<DeckSlide> {
  let current = slide
  const before = new Set(current.blocks.map((block) => block.id))
  let insertAt = anchor.index

  for (let i = 0; i < count; i++) {
    current = await createSlideBlock(projectId, slide.id, {
      revision: current.revision,
      type: 'text',
      parent_id: anchor.parentId,
      index: insertAt,
    })
    insertAt += 1
  }

  const newIds = current.blocks
    .filter((block) => !before.has(block.id) && block.type === 'text')
    .map((block) => block.id)
    .slice(-count)

  if (newIds.length !== count || current.layout_tree == null) {
    throw new Error('列插入未得到预期内容块')
  }

  const tree = current.layout_tree as FlexContainer
  const parent = findContainerById(tree, anchor.parentId)
  if (!parent) throw new Error('插入目标容器不存在')
  const wrapped = wrapBlockIdsAsColumns(tree, newIds)
  if (!wrapped) throw new Error('无法组装多列布局')

  return updateFlexLayout(projectId, slide.id, {
    revision: current.revision,
    layout_tree: wrapped,
  })
}

/**
 * 版式侧栏插入条：拖到画布落点插入；未拖动松手则落到选中块后/根末尾。
 */
export function BlockInsertPanel({
  projectId,
  slide,
  selectedBlockId,
  disabled,
}: {
  projectId: string
  slide: DeckSlide
  selectedBlockId: string | null
  disabled?: boolean
}) {
  if (slide.layout_mode !== 'flex' || slide.layout_tree == null) return null

  const tree = slide.layout_tree as FlexContainer
  const anchor = resolveInsertAnchor(tree, selectedBlockId)
  const handlers = getSlideSaveHandlers(slide.id)
  const locked = Boolean(disabled || !handlers)

  const insertBlock = (type: FlexBlockType) => {
    if (locked || !handlers) return
    handlers.commitCreateBlock({
      type,
      parent_id: anchor.parentId,
      index: anchor.index,
    })
  }

  // 入队即返回，失败由保存队列的状态提示；这里不做本地 try/catch 以免看起来已兜住
  const insertColumns = (count: 2 | 3) => {
    if (locked || !handlers) return
    handlers.commitMutate((current) =>
      insertColumnsAt(projectId, current, anchor, count),
    )
  }

  const beginDragBlock = (type: FlexBlockType, event: ReactPointerEvent) => {
    if (locked) return
    event.preventDefault()
    if (!requestInsertDrag(slide.id, { kind: 'block', type }, event.clientX, event.clientY)) {
      insertBlock(type)
    }
  }

  const beginDragColumns = (count: 2 | 3, event: ReactPointerEvent) => {
    if (locked) return
    event.preventDefault()
    if (
      !requestInsertDrag(
        slide.id,
        { kind: 'columns', count },
        event.clientX,
        event.clientY,
      )
    ) {
      insertColumns(count)
    }
  }

  return (
    <div className="rounded-xl border border-line bg-surface-soft/40 p-3">
      <p className="mb-2 text-[12px] font-medium text-ink-soft">插入内容</p>
      <InsertButtons
        locked={locked}
        onDragBlock={beginDragBlock}
        onDragColumns={beginDragColumns}
      />
    </div>
  )
}

function InsertButtons({
  locked,
  onDragBlock,
  onDragColumns,
}: {
  locked: boolean
  onDragBlock: (type: FlexBlockType, event: ReactPointerEvent) => void
  onDragColumns: (count: 2 | 3, event: ReactPointerEvent) => void
}) {
  return (
    <>
      <div className="grid grid-cols-3 gap-0.5">
        {BLOCK_BUTTONS.map(({ type, label, icon: Icon }) => (
          <button
            key={type}
            type="button"
            title={`拖入${label}，或轻点插入`}
            disabled={locked}
            onPointerDown={(event) => onDragBlock(type, event)}
            className={cn(
              'flex cursor-grab flex-col items-center gap-1 rounded-lg px-1.5 py-2.5 text-[11px] transition-colors',
              'text-ink-soft hover:bg-surface hover:text-ink active:cursor-grabbing',
              'disabled:opacity-40',
            )}
          >
            <Icon className="size-3.5" />
            {label}
          </button>
        ))}
      </div>
      <div className="mt-2 grid grid-cols-2 gap-0.5 border-t border-line pt-2">
        <button
          type="button"
          disabled={locked}
          title="拖入 2 列，或轻点插入"
          onPointerDown={(event) => onDragColumns(2, event)}
          className="flex cursor-grab items-center justify-center gap-1 rounded-lg px-2 py-1.5 text-[11px] text-ink-soft hover:bg-surface hover:text-ink active:cursor-grabbing disabled:opacity-40"
        >
          <Columns2 className="size-3.5" />
          2 列
        </button>
        <button
          type="button"
          disabled={locked}
          title="拖入 3 列，或轻点插入"
          onPointerDown={(event) => onDragColumns(3, event)}
          className="flex cursor-grab items-center justify-center gap-1 rounded-lg px-2 py-1.5 text-[11px] text-ink-soft hover:bg-surface hover:text-ink active:cursor-grabbing disabled:opacity-40"
        >
          <Columns3 className="size-3.5" />
          3 列
        </button>
      </div>
    </>
  )
}
