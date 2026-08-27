import { type DragEvent, useRef, useState } from 'react'

/**
 * 列表拖拽排序。大纲页与编辑器缩略图条共用一套手感，
 * 因此只维护"从哪来 / 悬停在哪"两个状态，落点由调用方决定怎么改数据。
 */
export function useDragSort(onMove: (from: number, to: number) => void, enabled = true) {
  const fromRef = useRef<number | null>(null)
  const [overIndex, setOverIndex] = useState<number | null>(null)
  const [draggingIndex, setDraggingIndex] = useState<number | null>(null)

  const reset = () => {
    fromRef.current = null
    setOverIndex(null)
    setDraggingIndex(null)
  }

  const itemProps = (index: number) => {
    if (!enabled) return {}
    return {
      draggable: true,
      onDragStart: (event: DragEvent<HTMLElement>) => {
        // 菜单等控件落在可拖拽父节点里时，按下会被当成拖拽起点，click 发不出去。
        // 不笼统排除 button：胶片缩略图本身就是 button，还要能拖。
        const target = event.target
        if (
          target instanceof Element &&
          target.closest('a, input, textarea, select, [data-no-drag]')
        ) {
          event.preventDefault()
          return
        }
        fromRef.current = index
        setDraggingIndex(index)
        event.dataTransfer.effectAllowed = 'move'
      },
      onDragOver: (event: DragEvent<HTMLElement>) => {
        if (fromRef.current == null) return
        event.preventDefault()
        setOverIndex(index)
      },
      onDragLeave: () => setOverIndex((current) => (current === index ? null : current)),
      onDrop: (event: DragEvent<HTMLElement>) => {
        event.preventDefault()
        const from = fromRef.current
        reset()
        if (from != null && from !== index) onMove(from, index)
      },
      onDragEnd: reset,
    }
  }

  return { itemProps, overIndex, draggingIndex }
}

export function moveItem<T>(items: T[], from: number, to: number): T[] {
  const next = [...items]
  const [moved] = next.splice(from, 1)
  next.splice(to, 0, moved)
  return next
}
