import { GripVertical } from 'lucide-react'
import {
  CORNER_HANDLES,
  EDGE_HANDLES,
  NARROW_BLOCK_HIDE_CORNER,
  gripOffsetStyle,
  pct,
} from '@/features/deck/flexEditGeometry'
import { useFlexPointerSession } from '@/features/deck/useFlexPointerSession'
import type { DeckSlide } from '@/features/deck/types'
import { cn } from '@/lib/utils'
import type { FlexContainer } from '@/render/flexLayout'

/**
 * flex 编辑叠加层：拖拽重排/侧栏拖入插入、行列拉伸。
 */
export function FlexEditLayer({
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
  /** 保存中：范围框与手柄照常显示，只是不接新手势，避免每次保存都闪一下 */
  busy?: boolean
  onPreviewTree?: (next: FlexContainer | null) => void
  onCommitTree: (next: FlexContainer) => void
  onSelectBlock?: (blockId: string) => void
  onDraggingChange?: (dragging: boolean) => void
}) {
  const {
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
  } = useFlexPointerSession({
    projectId,
    slide,
    tree,
    selectedBlockId,
    busy,
    onPreviewTree,
    onCommitTree,
    onSelectBlock,
    onDraggingChange,
  })

  return (
    <div ref={rootRef} className="pointer-events-none absolute inset-0 z-10">
      {rowDividers.map((divider) => {
        const key = `row:${divider.rowId}-${divider.leftIndex}`
        const active =
          (drag?.kind === 'ratio' &&
            drag.rowId === divider.rowId &&
            drag.leftIndex === divider.leftIndex) ||
          hoveredDividerKey === key
        return (
          <div
            key={key}
            role="separator"
            aria-orientation="vertical"
            title="拖动调整宽度"
            className={cn(
              hitClass,
              'absolute z-20 flex w-3 -translate-x-1/2 cursor-col-resize justify-center',
            )}
            style={{
              left: `${divider.x * 100}%`,
              top: `${divider.y * 100}%`,
              height: `${divider.h * 100}%`,
            }}
            onPointerEnter={() => setHoveredDividerKey(key)}
            onPointerLeave={() =>
              setHoveredDividerKey((current) => (current === key ? null : current))
            }
            onPointerDown={(event) => startRatio(divider, event)}
          >
            <span
              className={cn(
                'h-full w-0.5 rounded-full transition-colors',
                active || hoveredDividerKey === key ? 'bg-accent/60' : 'bg-transparent',
              )}
            />
          </div>
        )
      })}

      {columnDividers.map((divider) => {
        const key = `col:${divider.columnId}-${divider.topIndex}`
        const active =
          (drag?.kind === 'grow' &&
            drag.columnId === divider.columnId &&
            drag.topIndex === divider.topIndex) ||
          hoveredDividerKey === key
        return (
          <div
            key={key}
            role="separator"
            aria-orientation="horizontal"
            title="拖动调整高度"
            className={cn(
              hitClass,
              'absolute z-20 flex h-3 -translate-y-1/2 cursor-row-resize items-center',
            )}
            style={{
              left: `${divider.x * 100}%`,
              top: `${divider.y * 100}%`,
              width: `${divider.w * 100}%`,
            }}
            onPointerEnter={() => setHoveredDividerKey(key)}
            onPointerLeave={() =>
              setHoveredDividerKey((current) => (current === key ? null : current))
            }
            onPointerDown={(event) => startGrow(divider, event)}
          >
            <span
              className={cn(
                'w-full h-0.5 rounded-full transition-colors',
                active || hoveredDividerKey === key ? 'bg-accent/60' : 'bg-transparent',
              )}
            />
          </div>
        )
      })}

      {blockIds.map((blockId) => {
        if (draggingBlockId === blockId) return null
        const rect = placements.get(blockId)
        if (!rect) return null
        if (visibleHandleId !== blockId) return null
        const isSelected = selectedBlockId === blockId
        return (
          <button
            key={blockId}
            type="button"
            title="拖动排序；按住 Alt 微调位置，方向键 1pt / Shift 10pt"
            aria-label="拖动排序"
            className={cn(
              hitClass,
              'absolute z-20 grid size-5 place-items-center',
              'rounded-md border bg-surface text-ink-muted shadow-sm transition-opacity',
              'cursor-grab active:cursor-grabbing',
              isSelected
                ? 'border-accent/50 text-ink opacity-100'
                : 'border-line opacity-90 hover:opacity-100 hover:text-ink',
            )}
            style={gripOffsetStyle(rect)}
            onPointerDown={(event) => startReorder(blockId, event)}
          >
            <GripVertical className="size-3" />
          </button>
        )
      })}

      {selectedBlockId &&
        selectedRect &&
        (drag?.kind === 'grow' || drag?.kind === 'box' || drag?.kind === 'ratio') &&
        drag.activated && (
          <div
            aria-hidden
            className="pointer-events-none absolute z-[25] rounded-sm border border-accent/55 bg-accent/5"
            style={{
              left: pct(selectedRect.x),
              top: pct(selectedRect.y),
              width: pct(selectedRect.w),
              height: pct(selectedRect.h),
            }}
          />
        )}

      {selectedBlockId && selectedRect && !dragging && (
        <>
          {selectedRect.w >= NARROW_BLOCK_HIDE_CORNER &&
            CORNER_HANDLES.map((handle) => (
              <div
                key={handle.key}
                role="separator"
                title="拖动同时调整宽高"
                className={cn(
                  hitClass,
                  'absolute z-30 grid size-3 -translate-x-1/2 -translate-y-1/2 place-items-center',
                  handle.className,
                )}
                style={handle.style(selectedRect)}
                onPointerDown={(event) =>
                  beginCornerResize(selectedBlockId, handle.sideX, handle.sideY, event)
                }
              >
                <span className="size-2 rounded-[2px] border border-accent/70 bg-surface shadow-sm" />
              </div>
            ))}
          {/* 边手柄叠在角点之上（四角已 inset），保证上下边拖是纯纵向 */}
          {EDGE_HANDLES.map((handle) => (
            <div
              key={handle.key}
              role="separator"
              title={handle.title}
              className={cn(
                hitClass,
                'absolute z-[31] flex items-center justify-center',
                handle.className,
              )}
              style={handle.style(selectedRect)}
              onPointerDown={(event) =>
                beginBlockResize(selectedBlockId, handle.axis, handle.side, event)
              }
            >
              <span className={handle.barClassName} />
            </div>
          ))}
        </>
      )}

      {(drag?.kind === 'reorder' || (drag?.kind === 'insert' && drag.activated)) && (
        <div
          aria-hidden
          className="absolute z-40 overflow-hidden rounded-lg border border-accent/50 bg-surface/90 px-2 py-1.5 shadow-pop backdrop-blur-sm"
          style={{
            left: `${(drag.pointerX - drag.grabOffsetX) * 100}%`,
            top: `${(drag.pointerY - drag.grabOffsetY) * 100}%`,
            width: `${drag.ghostW * 100}%`,
            height: `${drag.ghostH * 100}%`,
            opacity: 0.92,
          }}
        >
          <div className="flex h-full items-start gap-1.5">
            <GripVertical className="mt-0.5 size-3 shrink-0 text-ink-muted" />
            <span className="line-clamp-3 text-[11px] leading-snug text-ink-soft">
              {ghostLabel}
            </span>
          </div>
        </div>
      )}

      {(drag?.kind === 'reorder' || (drag?.kind === 'insert' && drag.activated)) &&
        drag.drop && (
        <div
          aria-hidden
          className="absolute z-30 rounded-full bg-accent/80"
          style={
            drag.drop.line.axis === 'y'
              ? {
                  left: `${drag.drop.line.x * 100}%`,
                  top: `${drag.drop.line.y * 100}%`,
                  width: `${drag.drop.line.w * 100}%`,
                  height: 3,
                  transform: 'translateY(-1.5px)',
                }
              : {
                  left: `${drag.drop.line.x * 100}%`,
                  top: `${drag.drop.line.y * 100}%`,
                  width: 3,
                  height: `${drag.drop.line.h * 100}%`,
                  transform: 'translateX(-1.5px)',
                }
          }
        />
      )}
    </div>
  )
}
