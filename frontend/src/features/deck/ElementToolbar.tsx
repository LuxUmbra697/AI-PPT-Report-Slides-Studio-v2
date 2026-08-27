import {
  AlignCenter,
  AlignLeft,
  AlignRight,
  Bold,
  Italic,
  MoreHorizontal,
  RotateCcw,
  TableProperties,
  Trash2,
} from 'lucide-react'
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { cn } from '@/lib/utils'
import {
  type BlockStyle,
  COLOR_SWATCHES,
  isStyleEmpty,
  patchStyle,
  styleCapability,
} from '@/render/blockStyle'
import type { GroupPreset } from '@/render/flexLayout'
import { resolveColor } from '@/render/style'
import type { Block, EditableBlockCommit, TableBlock, Theme } from '@/render/types'

const PRESET_CHIPS: { value: GroupPreset; label: string }[] = [
  { value: 'solid_boxes', label: '实心' },
  { value: 'outline_boxes', label: '描边' },
  { value: 'side_line', label: '侧线' },
  { value: 'numbered_steps', label: '步骤' },
  { value: 'timeline', label: '时间线' },
]

interface ElementToolbarProps {
  articleEl: HTMLElement | null
  blockEl: HTMLElement | null
  block: Block
  theme: Theme
  disabled?: boolean
  onChange: (style: BlockStyle | null) => void
  /** 表格结构 / 图表数据等整包内容提交 */
  onCommitContent?: (change: EditableBlockCommit) => void
  /** flex 模式删除内容块 */
  onDelete?: () => void
  /** flex：选中块父容器的预设皮肤 */
  flexPreset?: GroupPreset | null
  onFlexPresetChange?: (preset: GroupPreset | null) => void
  onDismiss: () => void
}

const SIZE_STEP = 2

/**
 * 选中元素上方的浮动工具条。挂在 article 上定位，避免画布 overflow 裁切，
 * 也不随 zoom 把工具条字号一起放大。
 */
export function ElementToolbar({
  articleEl,
  blockEl,
  block,
  theme,
  disabled,
  onDelete,
  onCommitContent,
  flexPreset = null,
  onFlexPresetChange,
  onChange,
  onDismiss,
}: ElementToolbarProps) {
  const barRef = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null)
  const [colorOpen, setColorOpen] = useState<'color' | 'fill' | 'border' | null>(null)
  const [moreOpen, setMoreOpen] = useState(false)

  const style = block.style ?? null
  const caps = styleCapability(block.type)
  const supported = caps.text || caps.box || caps.borderOnly
  const showPreset = Boolean(onFlexPresetChange)
  const showTableOps = block.type === 'table' && Boolean(onCommitContent)
  const showBar = supported || Boolean(onDelete) || showPreset || showTableOps

  const resolvedSize = style?.size_pt != null ? Math.round(style.size_pt) : null

  const apply = (patch: Partial<BlockStyle>) => {
    if (disabled) return
    onChange(patchStyle(style, patch))
  }

  const reposition = () => {
    if (!articleEl || !blockEl || !barRef.current) return
    const articleBox = articleEl.getBoundingClientRect()
    const blockBox = blockEl.getBoundingClientRect()
    const barBox = barRef.current.getBoundingClientRect()
    const gap = 8
    let top = blockBox.top - articleBox.top - barBox.height - gap
    if (top < 4) {
      top = blockBox.bottom - articleBox.top + gap
    }
    let left = blockBox.left - articleBox.left + blockBox.width / 2 - barBox.width / 2
    left = Math.max(4, Math.min(left, articleBox.width - barBox.width - 4))
    const next = { left, top }
    // 坐标未变时不 setState，避免 layout effect 死循环把页面打崩
    setPos((prev) =>
      prev && Math.abs(prev.left - next.left) < 0.5 && Math.abs(prev.top - next.top) < 0.5
        ? prev
        : next,
    )
  }

  useLayoutEffect(() => {
    if (!showBar) return
    reposition()
  }, [showBar, articleEl, blockEl, block.id])

  useEffect(() => {
    if (!showBar || !articleEl || !blockEl) return
    const ro = new ResizeObserver(() => reposition())
    ro.observe(articleEl)
    ro.observe(blockEl)
    window.addEventListener('scroll', reposition, true)
    return () => {
      ro.disconnect()
      window.removeEventListener('scroll', reposition, true)
    }
  }, [articleEl, blockEl, showBar])

  useEffect(() => {
    if (!showBar) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onDismiss()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onDismiss, showBar])

  if (!showBar) return null

  const bold = (style?.weight ?? 400) >= 600
  const italic = Boolean(style?.italic)
  const align = style?.align ?? 'left'

  return (
    <div
      ref={barRef}
      role="toolbar"
      aria-label="元素样式"
      className="absolute z-50 flex items-center gap-0.5 rounded-xl border border-line bg-surface px-1.5 py-1 shadow-pop"
      style={{
        left: pos?.left ?? 0,
        top: pos?.top ?? 0,
        visibility: pos ? 'visible' : 'hidden',
      }}
      onPointerDown={(event) => event.stopPropagation()}
    >
      {caps.text && (
        <>
          <ToolBtn
            label="减小字号"
            disabled={disabled}
            onClick={() =>
              apply({
                size_pt: Math.max(8, (resolvedSize ?? 16) - SIZE_STEP),
              })
            }
          >
            <span className="text-[11px] font-semibold">A−</span>
          </ToolBtn>
          <span className="min-w-7 px-0.5 text-center text-[11px] text-ink-muted tabular-nums">
            {resolvedSize ?? '—'}
          </span>
          <ToolBtn
            label="增大字号"
            disabled={disabled}
            onClick={() =>
              apply({
                size_pt: Math.min(72, (resolvedSize ?? 16) + SIZE_STEP),
              })
            }
          >
            <span className="text-[11px] font-semibold">A+</span>
          </ToolBtn>
          <Sep />
          <ToolBtn
            label="加粗"
            pressed={bold}
            disabled={disabled}
            onClick={() => apply({ weight: bold ? 400 : 700 })}
          >
            <Bold className="size-3.5" />
          </ToolBtn>
          <ToolBtn
            label="斜体"
            pressed={italic}
            disabled={disabled}
            onClick={() => apply({ italic: !italic })}
          >
            <Italic className="size-3.5" />
          </ToolBtn>
          <ColorSwatch
            label="文字颜色"
            open={colorOpen === 'color'}
            theme={theme}
            value={style?.color ?? null}
            disabled={disabled}
            onToggle={() => setColorOpen((v) => (v === 'color' ? null : 'color'))}
            onPick={(value) => {
              apply({ color: value })
              setColorOpen(null)
            }}
          />
          <Sep />
          <ToolBtn
            label="左对齐"
            pressed={align === 'left'}
            disabled={disabled}
            onClick={() => apply({ align: 'left' })}
          >
            <AlignLeft className="size-3.5" />
          </ToolBtn>
          <ToolBtn
            label="居中"
            pressed={align === 'center'}
            disabled={disabled}
            onClick={() => apply({ align: 'center' })}
          >
            <AlignCenter className="size-3.5" />
          </ToolBtn>
          <ToolBtn
            label="右对齐"
            pressed={align === 'right'}
            disabled={disabled}
            onClick={() => apply({ align: 'right' })}
          >
            <AlignRight className="size-3.5" />
          </ToolBtn>
        </>
      )}

      {caps.box && (
        <>
          {caps.text && <Sep />}
          <ColorSwatch
            label="填充"
            open={colorOpen === 'fill'}
            theme={theme}
            value={style?.fill === 'none' ? null : (style?.fill ?? null)}
            allowNone
            disabled={disabled}
            onToggle={() => setColorOpen((v) => (v === 'fill' ? null : 'fill'))}
            onPick={(value) => {
              apply({ fill: value })
              setColorOpen(null)
            }}
          />
          <div className="relative">
            <ToolBtn
              label="更多"
              pressed={moreOpen}
              disabled={disabled}
              onClick={() => {
                setMoreOpen((v) => !v)
                setColorOpen(null)
              }}
            >
              <MoreHorizontal className="size-3.5" />
            </ToolBtn>
            {moreOpen && (
              <div className="absolute top-full left-0 z-50 mt-1 w-52 rounded-xl border border-line bg-surface p-3 shadow-pop">
                <label className="flex flex-col gap-1.5">
                  <span className="flex justify-between text-[11px] text-ink-muted">
                    <span>圆角</span>
                    <span className="tabular-nums">{Math.round(style?.radius_pt ?? 0)} pt</span>
                  </span>
                  <input
                    type="range"
                    min={0}
                    max={24}
                    step={1}
                    disabled={disabled}
                    value={Math.round(style?.radius_pt ?? 0)}
                    onChange={(event) => apply({ radius_pt: Number(event.target.value) })}
                    className="w-full accent-[var(--color-accent)]"
                  />
                </label>
                <label className="mt-3 flex flex-col gap-1.5">
                  <span className="flex justify-between text-[11px] text-ink-muted">
                    <span>内边距</span>
                    <span className="tabular-nums">{Math.round(style?.padding_pt ?? 0)} pt</span>
                  </span>
                  <input
                    type="range"
                    min={0}
                    max={32}
                    step={1}
                    disabled={disabled}
                    value={Math.round(style?.padding_pt ?? 0)}
                    onChange={(event) => apply({ padding_pt: Number(event.target.value) })}
                    className="w-full accent-[var(--color-accent)]"
                  />
                </label>
                <label className="mt-3 flex flex-col gap-1.5">
                  <span className="flex justify-between text-[11px] text-ink-muted">
                    <span>边框宽度</span>
                    <span className="tabular-nums">
                      {Math.round(style?.border_width_pt ?? 0)} pt
                    </span>
                  </span>
                  <input
                    type="range"
                    min={0}
                    max={4}
                    step={0.5}
                    disabled={disabled}
                    value={style?.border_width_pt ?? 0}
                    onChange={(event) => {
                      const width = Number(event.target.value)
                      apply({
                        border_width_pt: width,
                        border_color: width > 0 ? (style?.border_color ?? 'line') : null,
                      })
                    }}
                    className="w-full accent-[var(--color-accent)]"
                  />
                </label>
                {(style?.border_width_pt ?? 0) > 0 && (
                  <div className="mt-2">
                    <ColorSwatch
                      label="边框颜色"
                      open={colorOpen === 'border'}
                      theme={theme}
                      value={style?.border_color ?? 'line'}
                      disabled={disabled}
                      inline
                      onToggle={() => setColorOpen((v) => (v === 'border' ? null : 'border'))}
                      onPick={(value) => {
                        apply({ border_color: value })
                        setColorOpen(null)
                      }}
                    />
                  </div>
                )}
              </div>
            )}
          </div>
        </>
      )}

      {caps.borderOnly && (
        <>
          <label className="flex items-center gap-1.5 px-1 text-[11px] text-ink-muted">
            边框
            <input
              type="range"
              min={0}
              max={4}
              step={0.5}
              disabled={disabled}
              value={style?.border_width_pt ?? 0}
              onChange={(event) => {
                const width = Number(event.target.value)
                apply({
                  border_width_pt: width,
                  border_color: width > 0 ? (style?.border_color ?? 'line') : null,
                })
              }}
              className="w-16 accent-[var(--color-accent)]"
            />
          </label>
          {(style?.border_width_pt ?? 0) > 0 && (
            <ColorSwatch
              label="边框颜色"
              open={colorOpen === 'border'}
              theme={theme}
              value={style?.border_color ?? 'line'}
              disabled={disabled}
              onToggle={() => setColorOpen((v) => (v === 'border' ? null : 'border'))}
              onPick={(value) => {
                apply({ border_color: value })
                setColorOpen(null)
              }}
            />
          )}
        </>
      )}

      {!isStyleEmpty(style) && supported && (
        <>
          <Sep />
          <ToolBtn
            label="清除样式"
            disabled={disabled}
            onClick={() => onChange(null)}
          >
            <RotateCcw className="size-3.5" />
          </ToolBtn>
        </>
      )}

      {showTableOps && block.type === 'table' && onCommitContent && (
        <>
          {(supported || !isStyleEmpty(style)) && <Sep />}
          <TableStructureOps
            block={block}
            disabled={disabled}
            onCommitContent={onCommitContent}
          />
        </>
      )}

      {showPreset && (
        <>
          {(supported || !isStyleEmpty(style) || showTableOps) && <Sep />}
          <div
            role="group"
            aria-label="容器皮肤"
            className="flex items-center gap-0.5 px-0.5"
          >
            {PRESET_CHIPS.map((chip) => {
              const active = flexPreset === chip.value
              return (
                <button
                  key={chip.value}
                  type="button"
                  title={chip.label}
                  aria-label={chip.label}
                  aria-pressed={active}
                  disabled={disabled}
                  onClick={() =>
                    onFlexPresetChange?.(active ? null : chip.value)
                  }
                  className={cn(
                    'grid size-7 place-items-center rounded-md border transition-colors disabled:opacity-40',
                    active
                      ? 'border-accent bg-accent-soft'
                      : 'border-line hover:border-line-strong hover:bg-surface-soft',
                  )}
                >
                  <SkinChipPreview preset={chip.value} />
                </button>
              )
            })}
          </div>
        </>
      )}

      {onDelete && (
        <>
          {(supported || !isStyleEmpty(style) || showPreset || showTableOps) && <Sep />}
          <ToolBtn label="删除" disabled={disabled} onClick={onDelete}>
            <Trash2 className="size-3.5" />
          </ToolBtn>
        </>
      )}
    </div>
  )
}

function TableStructureOps({
  block,
  disabled,
  onCommitContent,
}: {
  block: TableBlock
  disabled?: boolean
  onCommitContent: (change: EditableBlockCommit) => void
}) {
  const replace = (header: string[], rows: string[][]) => {
    onCommitContent({ type: 'table', kind: 'replace', header, rows })
  }

  const cols = Math.max(block.header.length, 1)

  return (
    <div className="flex items-center gap-0.5" role="group" aria-label="表格结构">
      <TableProperties className="mx-0.5 size-3.5 text-ink-muted" />
      <ToolBtn
        label="加行"
        disabled={disabled}
        onClick={() =>
          replace(block.header, [...block.rows, Array.from({ length: cols }, () => '')])
        }
      >
        <span className="text-[10px] font-medium">+行</span>
      </ToolBtn>
      <ToolBtn
        label="加列"
        disabled={disabled}
        onClick={() =>
          replace(
            [...block.header, `列${block.header.length + 1}`],
            block.rows.map((row) => [...row, '']),
          )
        }
      >
        <span className="text-[10px] font-medium">+列</span>
      </ToolBtn>
      <ToolBtn
        label="删行"
        disabled={disabled || block.rows.length <= 1}
        onClick={() => replace(block.header, block.rows.slice(0, -1))}
      >
        <span className="text-[10px] font-medium">−行</span>
      </ToolBtn>
      <ToolBtn
        label="删列"
        disabled={disabled || block.header.length <= 1}
        onClick={() =>
          replace(
            block.header.slice(0, -1),
            block.rows.map((row) => row.slice(0, -1)),
          )
        }
      >
        <span className="text-[10px] font-medium">−列</span>
      </ToolBtn>
    </div>
  )
}

function ToolBtn({
  label,
  pressed,
  disabled,
  onClick,
  children,
}: {
  label: string
  pressed?: boolean
  disabled?: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={pressed}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'grid size-7 place-items-center rounded-lg transition-colors',
        pressed ? 'bg-accent-soft text-accent' : 'text-ink-soft hover:bg-surface-soft hover:text-ink',
        'disabled:opacity-40',
      )}
    >
      {children}
    </button>
  )
}

function Sep() {
  return <span aria-hidden className="mx-0.5 h-4 w-px bg-line" />
}

/** 工具条内的迷你皮肤预览 */
function SkinChipPreview({ preset }: { preset: GroupPreset }) {
  switch (preset) {
    case 'solid_boxes':
      return (
        <span aria-hidden className="flex gap-0.5">
          <span className="size-2 rounded-[2px] bg-ink/55" />
          <span className="size-2 rounded-[2px] bg-ink/35" />
        </span>
      )
    case 'outline_boxes':
      return (
        <span aria-hidden className="flex gap-0.5">
          <span className="size-2 rounded-[2px] border border-ink/55" />
          <span className="size-2 rounded-[2px] border border-ink/35" />
        </span>
      )
    case 'side_line':
      return (
        <span aria-hidden className="flex h-2.5 w-3.5 items-stretch gap-0.5">
          <span className="w-0.5 rounded-full bg-accent" />
          <span className="flex flex-1 flex-col justify-center gap-0.5">
            <span className="h-px w-full bg-ink/40" />
            <span className="h-px w-2/3 bg-ink/25" />
          </span>
        </span>
      )
    case 'numbered_steps':
      return (
        <span aria-hidden className="flex items-center gap-0.5">
          <span className="grid size-2 place-items-center rounded-full bg-accent text-[5px] leading-none text-white">
            1
          </span>
          <span className="h-px w-1.5 bg-ink/30" />
          <span className="grid size-2 place-items-center rounded-full bg-ink/35 text-[5px] leading-none text-white">
            2
          </span>
        </span>
      )
    case 'timeline':
      return (
        <span aria-hidden className="relative flex h-2.5 w-3.5 items-center">
          <span className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-ink/30" />
          <span className="relative z-10 size-1.5 rounded-full bg-accent" />
          <span className="relative z-10 ml-auto size-1.5 rounded-full bg-ink/40" />
        </span>
      )
  }
}

function ColorSwatch({
  label,
  open,
  theme,
  value,
  allowNone,
  disabled,
  inline,
  onToggle,
  onPick,
}: {
  label: string
  open: boolean
  theme: Theme
  value: string | null
  allowNone?: boolean
  disabled?: boolean
  inline?: boolean
  onToggle: () => void
  onPick: (value: string | null) => void
}) {
  const preview =
    value == null || value === 'none'
      ? 'transparent'
      : value.startsWith('#')
        ? value
        : resolveColor(theme, value)

  return (
    <div className={cn('relative', inline && 'static')}>
      <button
        type="button"
        title={label}
        aria-label={label}
        aria-expanded={open}
        disabled={disabled}
        onClick={onToggle}
        className="grid size-7 place-items-center rounded-lg text-ink-soft transition-colors hover:bg-surface-soft disabled:opacity-40"
      >
        <span
          className="size-3.5 rounded-full border border-line-strong"
          style={{
            background:
              preview === 'transparent'
                ? 'linear-gradient(135deg, transparent 45%, #ccc 45%, #ccc 55%, transparent 55%)'
                : preview,
          }}
        />
      </button>
      {open && (
        <div
          role="listbox"
          aria-label={label}
          className={cn(
            // 必须给明确宽度：挂在窄按钮上的 absolute 会被 shrink-to-fit 压扁，色块叠在一起点不到
            'z-50 w-52 rounded-xl border border-line bg-surface p-2 shadow-pop',
            inline ? 'relative mt-1' : 'absolute top-full left-1/2 mt-1 -translate-x-1/2',
          )}
        >
          <ul className="flex flex-col gap-0.5">
            {COLOR_SWATCHES.map(({ key, label: swatchLabel }) => {
              const selected = value === key
              return (
                <li key={key}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={selected}
                    title={swatchLabel}
                    onClick={() => onPick(key)}
                    className={cn(
                      'flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left transition-colors',
                      selected
                        ? 'bg-accent-soft text-accent'
                        : 'text-ink-soft hover:bg-surface-soft hover:text-ink',
                    )}
                  >
                    <span
                      aria-hidden
                      className="size-6 shrink-0 rounded-md border border-line-strong"
                      style={{ background: resolveColor(theme, key) }}
                    />
                    <span className="text-[12px]">{swatchLabel}</span>
                  </button>
                </li>
              )
            })}
          </ul>
          <div className="mt-2 flex items-center gap-2 border-t border-line pt-2">
            <label className="flex flex-1 cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-surface-soft">
              <input
                type="color"
                aria-label={`${label}自定义`}
                value={value?.startsWith('#') ? value : '#888888'}
                disabled={disabled}
                onChange={(event) => onPick(event.target.value.toUpperCase())}
                className="h-6 w-6 shrink-0 cursor-pointer rounded border border-line bg-surface p-0"
              />
              <span className="text-[12px] text-ink-muted">自定义</span>
            </label>
            {allowNone && (
              <button
                type="button"
                className="shrink-0 rounded-lg px-2 py-1.5 text-[12px] text-ink-muted hover:bg-surface-soft hover:text-accent"
                onClick={() => onPick('none')}
              >
                无填充
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
