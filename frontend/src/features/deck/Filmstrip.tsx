import {
  AlertTriangle,
  Copy,
  Loader2,
  Lock,
  MoreVertical,
  Plus,
  RotateCw,
  Trash2,
} from 'lucide-react'
import { MenuItem, MenuPopover } from '@/components/ui/MenuPopover'
import { useRetrySlide } from '@/features/deck/api'
import { type DeckSlide, slideDisplayTitle, toRenderSlide } from '@/features/deck/types'
import { useDragSort } from '@/hooks/useDragSort'
import { cn } from '@/lib/utils'
import { SlideView } from '@/render/SlideView'
import { CANVAS_HEIGHT_PT, CANVAS_WIDTH_PT, type Theme } from '@/render/types'

/**
 * 页面缩略图条：真实渲染每一页，而不是画占位方块。
 * 生成中禁止拖拽与增删——后端此时会整块覆盖 blocks，改结构必然撞车。
 */
export function Filmstrip({
  projectId,
  slides,
  theme,
  activeId,
  locked,
  busy,
  onSelect,
  onReorder,
  onInsert,
  onDuplicate,
  onDelete,
}: {
  projectId: string
  slides: DeckSlide[]
  theme: Theme
  activeId: string | null
  locked: boolean
  busy: boolean
  onSelect: (slideId: string) => void
  onReorder: (slideIds: string[]) => void
  onInsert: (afterSlideId: string | null) => void
  onDuplicate: (slideId: string) => void
  onDelete: (slideId: string) => void
}) {
  const drag = useDragSort((from, to) => {
    const ids = slides.map((slide) => slide.id)
    const [moved] = ids.splice(from, 1)
    ids.splice(to, 0, moved)
    onReorder(ids)
  }, !locked)

  return (
    <nav
      aria-label="页面列表"
      className="scrollbar-slim flex w-46 shrink-0 flex-col gap-2 overflow-y-auto border-r border-line bg-surface p-3"
    >
      {slides.map((slide, index) => (
        <FilmstripItem
          key={slide.id}
          projectId={projectId}
          slide={slide}
          theme={theme}
          index={index}
          active={slide.id === activeId}
          dragProps={drag.itemProps(index)}
          dragOver={drag.overIndex === index}
          dragging={drag.draggingIndex === index}
          locked={locked}
          // 删掉最后一页会让编辑器退回空态，且没有入口再建页
          canDelete={slides.length > 1}
          pending={busy}
          onSelect={() => onSelect(slide.id)}
          onInsert={() => onInsert(slide.id)}
          onDuplicate={() => onDuplicate(slide.id)}
          onDelete={() => onDelete(slide.id)}
        />
      ))}

      <button
        type="button"
        disabled={locked || busy}
        onClick={() => onInsert(null)}
        className="flex items-center justify-center gap-1.5 rounded-lg border border-line border-dashed py-2 text-[12px] text-ink-muted transition-colors hover:border-accent hover:text-accent disabled:opacity-50"
      >
        <Plus className="size-3.5" />
        新增页面
      </button>
    </nav>
  )
}

function FilmstripItem({
  projectId,
  slide,
  theme,
  index,
  active,
  dragProps,
  dragOver,
  dragging,
  locked,
  canDelete,
  pending,
  onSelect,
  onInsert,
  onDuplicate,
  onDelete,
}: {
  projectId: string
  slide: DeckSlide
  theme: Theme
  index: number
  active: boolean
  dragProps: Record<string, unknown>
  dragOver: boolean
  dragging: boolean
  locked: boolean
  canDelete: boolean
  pending: boolean
  onSelect: () => void
  onInsert: () => void
  onDuplicate: () => void
  onDelete: () => void
}) {
  const retry = useRetrySlide(projectId)
  const warnings = slide.issues.filter((issue) => issue.severity === 'warning').length
  const edited = slide.blocks.some((block) => block.locked)

  return (
    <div {...dragProps} className={cn('group relative', dragging && 'opacity-50')}>
      <button
        type="button"
        aria-current={active}
        onClick={onSelect}
        className={cn(
          'block w-full overflow-hidden rounded-lg border bg-surface text-left transition-all',
          active
            ? 'border-accent ring-1 ring-accent'
            : dragOver
              ? 'border-accent'
              : 'border-line hover:border-line-strong',
        )}
      >
        <div style={{ aspectRatio: `${CANVAS_WIDTH_PT} / ${CANVAS_HEIGHT_PT}` }}>
          {slide.status === 'ready' ? (
            <SlideView slide={toRenderSlide(slide)} theme={theme} slideIndex={index} />
          ) : (
            <Placeholder status={slide.status} />
          )}
        </div>
      </button>

      {!locked && (
        <PageMenu
          busy={pending}
          canDelete={canDelete}
          onInsert={onInsert}
          onDuplicate={onDuplicate}
          onDelete={onDelete}
        />
      )}

      <div className="mt-1 flex items-center gap-1.5 px-0.5">
        <span className="w-4 text-[11px] text-ink-muted tabular-nums">{index + 1}</span>
        <span className="min-w-0 flex-1 truncate text-[11px] text-ink-soft">
          {slideDisplayTitle(slide)}
        </span>
        {slide.status === 'generating' && <Loader2 className="size-3 animate-spin text-accent" />}
        {edited && (
          <span title="已人工修改，AI 不会覆盖" className="text-ink-muted">
            <Lock className="size-3" />
          </span>
        )}
        {slide.status === 'ready' && warnings > 0 && (
          <span title={`${warnings} 处内容偏长`} className="text-warning">
            <AlertTriangle className="size-3" />
          </span>
        )}
      </div>

      {slide.status === 'failed' && (
        <button
          type="button"
          data-no-drag
          disabled={locked || retry.isPending}
          onClick={() => retry.mutate(slide.id)}
          className="mt-1 flex w-full items-center justify-center gap-1 rounded-md bg-negative/8 py-1 text-[11px] text-negative transition-colors hover:bg-negative/15 disabled:opacity-50"
        >
          <RotateCw className={cn('size-3', retry.isPending && 'animate-spin')} />
          {retry.isPending ? '重试中…' : '重试这一页'}
        </button>
      )}
    </div>
  )
}

/** 缩略图右上角的页面操作入口：悬浮或菜单展开时才现身，免得盖住画面 */
function PageMenu({
  busy,
  canDelete,
  onInsert,
  onDuplicate,
  onDelete,
}: {
  busy: boolean
  canDelete: boolean
  onInsert: () => void
  onDuplicate: () => void
  onDelete: () => void
}) {
  return (
    <div data-no-drag className="absolute top-1 right-1 z-10">
      <MenuPopover
        label="页面操作"
        className="w-40"
        trigger={({ open, toggle }) => (
          <button
            type="button"
            aria-label="页面操作"
            aria-expanded={open}
            onClick={toggle}
            className={cn(
              'grid size-6 place-items-center rounded-md bg-surface/90 text-ink-muted ring-1 ring-line transition-opacity hover:text-ink',
              open ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 focus-visible:opacity-100',
            )}
          >
            <MoreVertical className="size-3.5" />
          </button>
        )}
      >
        {({ close }) => (
          <>
            <MenuItem
              icon={Plus}
              disabled={busy}
              onSelect={() => {
                close()
                onInsert()
              }}
            >
              在此后插入空白页
            </MenuItem>
            <MenuItem
              icon={Copy}
              disabled={busy}
              onSelect={() => {
                close()
                onDuplicate()
              }}
            >
              复制本页
            </MenuItem>
            <MenuItem
              icon={Trash2}
              danger
              disabled={busy || !canDelete}
              onSelect={() => {
                close()
                onDelete()
              }}
            >
              删除本页
            </MenuItem>
          </>
        )}
      </MenuPopover>
    </div>
  )
}

function Placeholder({ status }: { status: DeckSlide['status'] }) {
  if (status === 'failed') {
    return (
      <div className="grid h-full place-items-center bg-negative/[0.05]">
        <AlertTriangle className="size-4 text-negative/70" />
      </div>
    )
  }

  const pulse = status === 'generating'
  return (
    <div className="flex h-full flex-col justify-end gap-1.5 bg-surface-soft p-3">
      <span className={cn('h-1.5 w-1/2 rounded-full', pulse ? 'animate-pulse bg-accent/40' : 'bg-line-strong')} />
      <span className={cn('h-1 w-4/5 rounded-full bg-line', pulse && 'animate-pulse')} />
      <span className={cn('h-1 w-3/5 rounded-full bg-line', pulse && 'animate-pulse')} />
    </div>
  )
}
