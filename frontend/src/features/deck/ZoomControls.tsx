import { Minus, Plus } from 'lucide-react'

export function ZoomControls({
  zoom,
  canZoomIn,
  canZoomOut,
  onZoom,
}: {
  zoom: number
  canZoomIn: boolean
  canZoomOut: boolean
  onZoom: (delta: 1 | -1) => void
}) {
  return (
    <div className="flex items-center gap-1">
      <button
        type="button"
        aria-label="缩小"
        disabled={!canZoomOut}
        onClick={() => onZoom(-1)}
        className="grid size-7 place-items-center rounded-md text-ink-muted transition-colors hover:bg-surface-soft hover:text-ink disabled:opacity-30"
      >
        <Minus className="size-3.5" />
      </button>
      <span className="w-10 text-center text-xs text-ink-muted tabular-nums">
        {Math.round(zoom * 100)}%
      </span>
      <button
        type="button"
        aria-label="放大"
        disabled={!canZoomIn}
        onClick={() => onZoom(1)}
        className="grid size-7 place-items-center rounded-md text-ink-muted transition-colors hover:bg-surface-soft hover:text-ink disabled:opacity-30"
      >
        <Plus className="size-3.5" />
      </button>
    </div>
  )
}
