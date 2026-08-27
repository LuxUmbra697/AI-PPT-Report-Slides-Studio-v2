import { Plus, Trash2 } from 'lucide-react'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { cn } from '@/lib/utils'
import type { ChartBlock, EditableBlockCommit } from '@/render/types'

const CHART_TYPES: Array<{ value: ChartBlock['chart_type']; label: string }> = [
  { value: 'bar', label: '条形' },
  { value: 'column', label: '柱状' },
  { value: 'line', label: '折线' },
  { value: 'pie', label: '饼图' },
]

/**
 * 选中图表时的数据编辑浮层：改类型、类别与系列数值。
 */
export function ChartDataEditor({
  articleEl,
  blockEl,
  block,
  disabled,
  onCommit,
  onDismiss,
}: {
  articleEl: HTMLElement | null
  blockEl: HTMLElement | null
  block: ChartBlock
  disabled?: boolean
  onCommit: (change: EditableBlockCommit) => void
  onDismiss: () => void
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null)
  const [chartType, setChartType] = useState(block.chart_type)
  const [categories, setCategories] = useState([...block.categories])
  const [series, setSeries] = useState(
    block.series.map((item) => ({
      name: item.name,
      values: [...item.values],
    })),
  )
  const [unit, setUnit] = useState(block.unit ?? '')

  useEffect(() => {
    setChartType(block.chart_type)
    setCategories([...block.categories])
    setSeries(
      block.series.map((item) => ({
        name: item.name,
        values: [...item.values],
      })),
    )
    setUnit(block.unit ?? '')
  }, [block])

  const reposition = () => {
    if (!articleEl || !blockEl || !panelRef.current) return
    const articleBox = articleEl.getBoundingClientRect()
    const blockBox = blockEl.getBoundingClientRect()
    const panelBox = panelRef.current.getBoundingClientRect()
    let top = blockBox.bottom - articleBox.top + 8
    if (top + panelBox.height > articleBox.height - 4) {
      top = Math.max(4, blockBox.top - articleBox.top - panelBox.height - 8)
    }
    let left = blockBox.left - articleBox.left
    left = Math.max(4, Math.min(left, articleBox.width - panelBox.width - 4))
    const next = { left, top }
    setPos((prev) =>
      prev && Math.abs(prev.left - next.left) < 0.5 && Math.abs(prev.top - next.top) < 0.5
        ? prev
        : next,
    )
  }

  useLayoutEffect(() => {
    reposition()
  }, [articleEl, blockEl, block.id, categories.length, series.length])

  useEffect(() => {
    if (!articleEl || !blockEl) return
    const ro = new ResizeObserver(() => reposition())
    ro.observe(articleEl)
    ro.observe(blockEl)
    window.addEventListener('scroll', reposition, true)
    return () => {
      ro.disconnect()
      window.removeEventListener('scroll', reposition, true)
    }
  }, [articleEl, blockEl])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onDismiss()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onDismiss])

  const syncCols = (nextCats: string[]) => {
    setCategories(nextCats)
    setSeries((current) =>
      current.map((item) => ({
        ...item,
        values: nextCats.map((_, index) => item.values[index] ?? 0),
      })),
    )
  }

  const apply = () => {
    if (disabled) return
    const cleanCats = categories.map((item) => item.trim() || '类别')
    const cleanSeries = series.map((item, index) => ({
      name: item.name.trim() || `系列${index + 1}`,
      values: cleanCats.map((_, col) => Number(item.values[col]) || 0),
    }))
    onCommit({
      type: 'chart',
      chart_type: chartType,
      categories: cleanCats,
      series: cleanSeries.length ? cleanSeries : [{ name: '系列1', values: cleanCats.map(() => 0) }],
      unit: unit.trim() || null,
    })
  }

  return (
    <div
      ref={panelRef}
      className="absolute z-40 w-[22rem] rounded-xl border border-line bg-surface p-3 shadow-pop"
      style={pos ? { left: pos.left, top: pos.top } : { visibility: 'hidden' }}
      onPointerDown={(event) => event.stopPropagation()}
    >
      <div className="mb-2 flex items-center gap-2">
        <span className="flex-1 text-[12px] font-medium text-ink-soft">图表数据</span>
        <div className="flex gap-0.5">
          {CHART_TYPES.map((option) => (
            <button
              key={option.value}
              type="button"
              disabled={disabled}
              aria-pressed={chartType === option.value}
              onClick={() => setChartType(option.value)}
              className={cn(
                'rounded-md px-1.5 py-0.5 text-[11px] transition-colors disabled:opacity-40',
                chartType === option.value
                  ? 'bg-accent-soft text-accent'
                  : 'text-ink-muted hover:bg-surface-soft',
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <label className="mb-2 flex items-center gap-2 text-[11px] text-ink-muted">
        单位
        <input
          value={unit}
          disabled={disabled}
          onChange={(event) => setUnit(event.target.value)}
          className="min-w-0 flex-1 rounded-md border border-line bg-surface px-2 py-1 text-[12px] text-ink outline-none focus:border-accent"
          placeholder="可选"
        />
      </label>

      <div className="scrollbar-slim max-h-56 space-y-2 overflow-y-auto">
        <div className="grid gap-1" style={{ gridTemplateColumns: `4.5rem repeat(${categories.length}, minmax(3.5rem, 1fr))` }}>
          <span className="text-[10px] text-ink-muted">系列 \\ 类</span>
          {categories.map((cat, index) => (
            <input
              key={`cat-${index}`}
              value={cat}
              disabled={disabled}
              onChange={(event) => {
                const next = [...categories]
                next[index] = event.target.value
                setCategories(next)
              }}
              className="rounded border border-line px-1 py-0.5 text-[11px] outline-none focus:border-accent"
            />
          ))}
          {series.map((item, rowIndex) => (
            <div key={`s-${rowIndex}`} className="contents">
              <input
                value={item.name}
                disabled={disabled}
                onChange={(event) => {
                  setSeries((current) =>
                    current.map((row, i) =>
                      i === rowIndex ? { ...row, name: event.target.value } : row,
                    ),
                  )
                }}
                className="rounded border border-line px-1 py-0.5 text-[11px] outline-none focus:border-accent"
              />
              {categories.map((_, colIndex) => (
                <input
                  key={`v-${rowIndex}-${colIndex}`}
                  type="number"
                  value={item.values[colIndex] ?? 0}
                  disabled={disabled}
                  onChange={(event) => {
                    const value = Number(event.target.value)
                    setSeries((current) =>
                      current.map((row, i) => {
                        if (i !== rowIndex) return row
                        const values = [...row.values]
                        values[colIndex] = Number.isFinite(value) ? value : 0
                        return { ...row, values }
                      }),
                    )
                  }}
                  className="rounded border border-line px-1 py-0.5 text-[11px] outline-none focus:border-accent"
                />
              ))}
            </div>
          ))}
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          disabled={disabled}
          onClick={() => syncCols([...categories, `类别${categories.length + 1}`])}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-ink-soft hover:bg-surface-soft disabled:opacity-40"
        >
          <Plus className="size-3" />
          类别
        </button>
        <button
          type="button"
          disabled={disabled || categories.length <= 1}
          onClick={() => syncCols(categories.slice(0, -1))}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-ink-soft hover:bg-surface-soft disabled:opacity-40"
        >
          <Trash2 className="size-3" />
          类别
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() =>
            setSeries((current) => [
              ...current,
              { name: `系列${current.length + 1}`, values: categories.map(() => 0) },
            ])
          }
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-ink-soft hover:bg-surface-soft disabled:opacity-40"
        >
          <Plus className="size-3" />
          系列
        </button>
        <button
          type="button"
          disabled={disabled || series.length <= 1}
          onClick={() => setSeries((current) => current.slice(0, -1))}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-ink-soft hover:bg-surface-soft disabled:opacity-40"
        >
          <Trash2 className="size-3" />
          系列
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={apply}
          className="ml-auto rounded-lg bg-accent px-2.5 py-1 text-[11px] font-medium text-white hover:opacity-90 disabled:opacity-40"
        >
          应用
        </button>
      </div>
    </div>
  )
}
