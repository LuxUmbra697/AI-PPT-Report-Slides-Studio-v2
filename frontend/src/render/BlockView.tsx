import { useRef, useState, type CSSProperties } from 'react'
import { boxCss, mergeTextCss } from '@/render/blockStyle'
import { ChartView } from '@/render/ChartView'
import { EditableText } from '@/render/EditableText'
import { pt, resolveColor } from '@/render/style'
import type {
  Block,
  BulletsBlock,
  CalloutBlock,
  CardsBlock,
  EditableBlockCommit,
  ImageBlock,
  KpiBlock,
  Slot,
  TableBlock,
  TextBlock,
  TextStyleName,
  Theme,
} from '@/render/types'

/** 标题类与单元格按单行约束；正文允许换行 */
const MULTILINE_STYLES = new Set<TextStyleName>(['body', 'bullet'])

interface BlockProps<T> {
  block: T
  slot: Slot
  theme: Theme
  editable?: boolean
  onCommit?: (blockId: string, body: EditableBlockCommit) => void
  onSelect?: (blockId: string) => void
}

function TextView({ block, slot, theme, editable, onCommit, onSelect }: BlockProps<TextBlock>) {
  const styleName = slot.text_style ?? 'body'
  const style = mergeTextCss(theme, styleName, block.style)
  const chrome = boxCss(theme, block.style)

  if (!editable || !onCommit) {
    return (
      <div style={chrome}>
        <p style={{ ...style, margin: 0 }}>{block.text}</p>
      </div>
    )
  }

  return (
    <div style={chrome}>
      <p style={{ ...style, margin: 0 }}>
        <EditableText
          value={block.text}
          ariaLabel="编辑文字"
          multiline={MULTILINE_STYLES.has(styleName)}
          style={style}
          onFocus={() => onSelect?.(block.id)}
          onCommit={(text) => onCommit(block.id, { type: 'text', text })}
        />
      </p>
    </div>
  )
}

function BulletMarker({ theme, index }: { theme: Theme; index: number }) {
  const accent = resolveColor(theme, 'accent')

  if (theme.shape.bullet_marker === 'index') {
    return (
      <span
        style={{
          color: accent,
          flexShrink: 0,
          width: pt(22),
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {String(index + 1).padStart(2, '0')}
      </span>
    )
  }

  if (theme.shape.bullet_marker === 'dot') {
    return (
      <span
        style={{
          flexShrink: 0,
          width: pt(6),
          height: pt(6),
          marginRight: pt(14),
          marginTop: pt(9),
          borderRadius: '50%',
          background: accent,
        }}
      />
    )
  }

  return (
    <span
      style={{
        flexShrink: 0,
        width: pt(14),
        height: pt(1.5),
        marginRight: pt(14),
        marginTop: pt(11),
        background: accent,
      }}
    />
  )
}

function BulletsView({
  block,
  slot,
  theme,
  editable,
  onCommit,
  onSelect,
}: BlockProps<BulletsBlock>) {
  const textStyle = mergeTextCss(theme, slot.text_style ?? 'bullet', block.style)
  const chrome = boxCss(theme, block.style)
  const [focus, setFocus] = useState<{ index: number; token: number; caret: 'start' | 'end' } | null>(
    null,
  )
  const focusSeq = useRef(0)

  const jumpTo = (index: number, caret: 'start' | 'end' = 'start') => {
    focusSeq.current += 1
    setFocus({ index, token: focusSeq.current, caret })
  }

  return (
    <div style={chrome}>
      <ul
        style={{
          ...textStyle,
          listStyle: 'none',
          margin: 0,
          padding: 0,
          display: 'flex',
          flexDirection: 'column',
          gap: pt(12),
        }}
      >
        {block.items.map((item, index) => (
          <li key={`${block.id}-${index}`} style={{ display: 'flex', alignItems: 'flex-start' }}>
            <BulletMarker theme={theme} index={index} />
            {editable && onCommit ? (
              <EditableText
                value={item}
                ariaLabel={`编辑要点 ${index + 1}`}
                style={{ ...textStyle, flex: 1 }}
                focusToken={focus?.index === index ? focus.token : null}
                focusCaret={focus?.index === index ? focus.caret : 'start'}
                onFocus={() => onSelect?.(block.id)}
                onCommit={(text) => onCommit(block.id, { type: 'bullets', index, text })}
                onEnter={() => {
                  onCommit(block.id, { type: 'bullets', kind: 'insert', index })
                  jumpTo(index + 1, 'start')
                }}
                onBackspaceWhenEmpty={() => {
                  if (block.items.length <= 1) return
                  onCommit(block.id, { type: 'bullets', kind: 'remove', index })
                  jumpTo(Math.max(0, index - 1), 'end')
                }}
              />
            ) : (
              <span>{item}</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

/** 图源缺失时的降级图形，按主题色绘制，不依赖网络 */
function ImagePlaceholder({ theme, alt }: { theme: Theme; alt: string }) {
  return (
    <svg
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      role="img"
      aria-label={alt}
      style={{ width: '100%', height: '100%', display: 'block' }}
    >
      <rect width="100" height="100" fill={resolveColor(theme, 'accent_soft')} />
      <circle cx="74" cy="28" r="30" fill={resolveColor(theme, 'accent')} opacity="0.22" />
      <circle cx="74" cy="28" r="18" fill={resolveColor(theme, 'accent')} opacity="0.3" />
      <path
        d="M0 78 L34 52 L58 70 L100 40 L100 100 L0 100 Z"
        fill={resolveColor(theme, 'accent')}
        opacity="0.16"
      />
      <rect x="8" y="86" width="18" height="1.2" fill={resolveColor(theme, 'accent')} />
    </svg>
  )
}

function ImageView({ block, theme }: BlockProps<ImageBlock>) {
  const border =
    block.style?.border_color != null &&
    block.style?.border_width_pt != null &&
    block.style.border_width_pt > 0
      ? {
          border: `${pt(block.style.border_width_pt)} solid ${
            block.style.border_color.startsWith('#')
              ? block.style.border_color
              : resolveColor(theme, block.style.border_color)
          }`,
          boxSizing: 'border-box' as const,
          width: '100%',
          height: '100%',
        }
      : { width: '100%', height: '100%' }

  if (!block.url) {
    return (
      <div style={border}>
        <ImagePlaceholder theme={theme} alt={block.alt} />
      </div>
    )
  }
  return (
    <img
      src={block.url}
      alt={block.alt}
      style={{ ...border, objectFit: 'cover', display: 'block' }}
    />
  )
}

function TableView({ block, theme, editable, onCommit, onSelect }: BlockProps<TableBlock>) {
  const headerStyle = mergeTextCss(theme, 'table_header', block.style)
  const cellStyle = mergeTextCss(theme, 'table_cell', block.style)
  const border = `${pt(theme.shape.border_width_pt)} solid ${resolveColor(theme, 'line')}`
  const cellPadding: CSSProperties = { padding: `${pt(9)} ${pt(12)}`, textAlign: 'left' }
  if (block.style?.align) {
    cellPadding.textAlign = block.style.align
  }

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
      <thead>
        <tr>
          {block.header.map((cell, index) => (
            <th
              key={`h-${index}`}
              style={{
                ...headerStyle,
                ...cellPadding,
                borderBottom: `${pt(1.5)} solid ${resolveColor(theme, 'accent')}`,
              }}
            >
              {editable && onCommit ? (
                <EditableText
                  value={cell}
                  multiline
                  ariaLabel={`编辑表头 ${index + 1}`}
                  style={headerStyle}
                  onFocus={() => onSelect?.(block.id)}
                  onCommit={(text) =>
                    onCommit(block.id, { type: 'table', kind: 'header', index, text })
                  }
                />
              ) : (
                cell
              )}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {block.rows.map((row, rowIndex) => (
          <tr key={`r-${rowIndex}`}>
            {row.map((cell, cellIndex) => (
              <td
                key={`c-${rowIndex}-${cellIndex}`}
                style={{ ...cellStyle, ...cellPadding, borderBottom: border }}
              >
                {editable && onCommit ? (
                  <EditableText
                    value={cell}
                    multiline
                    ariaLabel={`编辑单元格 ${rowIndex + 1}-${cellIndex + 1}`}
                    style={cellStyle}
                    onFocus={() => onSelect?.(block.id)}
                    onCommit={(text) =>
                      onCommit(block.id, {
                        type: 'table',
                        kind: 'cell',
                        row: rowIndex,
                        col: cellIndex,
                        text,
                      })
                    }
                  />
                ) : (
                  cell
                )}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function KpiView({ block, theme, editable, onCommit, onSelect }: BlockProps<KpiBlock>) {
  const valueStyle = mergeTextCss(theme, 'kpi_value', block.style)
  const labelStyle = mergeTextCss(theme, 'kpi_label', block.style)
  const noteStyle = mergeTextCss(theme, 'kpi_note', block.style)
  const chrome = boxCss(theme, block.style)
  // 衬线大字号侧轴承常超出 em 盒；窄列 + 槽位裁切时需整块留白（盖过 chrome.padding）
  const shell: CSSProperties = {
    ...chrome,
    display: 'flex',
    flexDirection: 'column',
    gap: pt(8),
    boxSizing: 'border-box',
    width: '100%',
    height: '100%',
    minWidth: 0,
    padding: undefined,
    paddingInline: pt(14),
    paddingBlock: pt(8),
    overflow: 'visible',
  }
  const valueCss = {
    ...valueStyle,
    whiteSpace: 'nowrap' as const,
    overflow: 'visible' as const,
    // 再给首字一点光学边距，避免 Instrument Serif「5」贴边
    paddingInlineStart: '0.12em',
  }

  if (!editable || !onCommit) {
    return (
      <div style={shell}>
        <span style={valueCss}>{block.value}</span>
        <span style={labelStyle}>{block.label}</span>
        {block.note && <span style={noteStyle}>{block.note}</span>}
      </div>
    )
  }

  return (
    <div style={shell}>
      <EditableText
        value={block.value}
        ariaLabel="编辑指标数值"
        style={valueCss}
        onFocus={() => onSelect?.(block.id)}
        onCommit={(text) => onCommit(block.id, { type: 'kpi', field: 'value', text })}
      />
      <EditableText
        value={block.label}
        ariaLabel="编辑指标标签"
        style={labelStyle}
        onFocus={() => onSelect?.(block.id)}
        onCommit={(text) => onCommit(block.id, { type: 'kpi', field: 'label', text })}
      />
      <EditableText
        value={block.note ?? ''}
        ariaLabel="编辑指标备注"
        style={noteStyle}
        onFocus={() => onSelect?.(block.id)}
        onCommit={(text) => onCommit(block.id, { type: 'kpi', field: 'note', text })}
      />
    </div>
  )
}

const CARD_GAP_PT = 16
const CARD_PAD_PT = 12

function CardsView({ block, theme, editable, onCommit, onSelect }: BlockProps<CardsBlock>) {
  const titleStyle = mergeTextCss(theme, 'subtitle', block.style)
  const descStyle = mergeTextCss(theme, 'body', block.style)
  const chrome = boxCss(theme, block.style)
  const surface = resolveColor(theme, 'surface')
  const radius = theme.shape.radius_pt

  return (
    <div
      style={{
        ...chrome,
        display: 'flex',
        flexDirection: 'row',
        gap: pt(CARD_GAP_PT),
        width: '100%',
        height: '100%',
        boxSizing: 'border-box',
      }}
    >
      {block.items.map((item, index) => (
        <div
          key={`${block.id}-${index}`}
          style={{
            flex: 1,
            minWidth: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: pt(6),
            padding: pt(CARD_PAD_PT),
            background: surface,
            borderRadius: pt(radius),
            boxSizing: 'border-box',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: pt(6) }}>
            {item.icon ? (
              <span style={{ ...titleStyle, flexShrink: 0 }} aria-hidden>
                {item.icon}
              </span>
            ) : null}
            {editable && onCommit ? (
              <EditableText
                value={item.title}
                ariaLabel={`编辑卡片标题 ${index + 1}`}
                style={{ ...titleStyle, flex: 1 }}
                onFocus={() => onSelect?.(block.id)}
                onCommit={(text) =>
                  onCommit(block.id, { type: 'cards', index, field: 'title', text })
                }
              />
            ) : (
              <span style={titleStyle}>{item.title}</span>
            )}
          </div>
          {editable && onCommit ? (
            <EditableText
              value={item.desc}
              ariaLabel={`编辑卡片描述 ${index + 1}`}
              multiline
              style={descStyle}
              onFocus={() => onSelect?.(block.id)}
              onCommit={(text) =>
                onCommit(block.id, { type: 'cards', index, field: 'desc', text })
              }
            />
          ) : (
            <span style={descStyle}>{item.desc}</span>
          )}
        </div>
      ))}
    </div>
  )
}

function CalloutView({
  block,
  theme,
  editable,
  onCommit,
  onSelect,
}: BlockProps<CalloutBlock>) {
  const isSource = block.variant === 'source'
  const textStyle = mergeTextCss(theme, isSource ? 'caption' : 'body', block.style)
  const chrome = boxCss(theme, block.style)
  const accent = resolveColor(theme, 'accent')
  const surface = resolveColor(theme, 'surface')
  const background = resolveColor(theme, 'background')
  const fill = isSource
    ? `color-mix(in srgb, ${surface} 35%, ${background})`
    : `color-mix(in srgb, ${accent} 18%, ${background})`

  return (
    <div
      style={{
        ...chrome,
        display: 'flex',
        alignItems: 'flex-start',
        gap: pt(8),
        width: '100%',
        height: '100%',
        padding: `${pt(CARD_PAD_PT * 0.75)} ${pt(CARD_PAD_PT)}`,
        background: chrome.background ?? fill,
        borderRadius: pt(theme.shape.radius_pt),
        boxSizing: 'border-box',
      }}
    >
      {block.icon ? (
        <span style={{ ...textStyle, flexShrink: 0 }} aria-hidden>
          {block.icon}
        </span>
      ) : null}
      {editable && onCommit ? (
        <EditableText
          value={block.text}
          ariaLabel="编辑提示文字"
          multiline
          style={{ ...textStyle, flex: 1 }}
          onFocus={() => onSelect?.(block.id)}
          onCommit={(text) => onCommit(block.id, { type: 'callout', text })}
        />
      ) : (
        <span style={{ ...textStyle, flex: 1 }}>{block.text}</span>
      )}
    </div>
  )
}

export function BlockView({
  block,
  slot,
  theme,
  editable,
  onCommit,
  onSelect,
}: BlockProps<Block>) {
  switch (block.type) {
    case 'text':
      return (
        <TextView
          block={block}
          slot={slot}
          theme={theme}
          editable={editable}
          onCommit={onCommit}
          onSelect={onSelect}
        />
      )
    case 'bullets':
      return (
        <BulletsView
          block={block}
          slot={slot}
          theme={theme}
          editable={editable}
          onCommit={onCommit}
          onSelect={onSelect}
        />
      )
    case 'image':
      return <ImageView block={block} slot={slot} theme={theme} />
    case 'chart':
      return <ChartView block={block} slot={slot} theme={theme} />
    case 'table':
      return (
        <TableView
          block={block}
          slot={slot}
          theme={theme}
          editable={editable}
          onCommit={onCommit}
          onSelect={onSelect}
        />
      )
    case 'kpi':
      return (
        <KpiView
          block={block}
          slot={slot}
          theme={theme}
          editable={editable}
          onCommit={onCommit}
          onSelect={onSelect}
        />
      )
    case 'cards':
      return (
        <CardsView
          block={block}
          slot={slot}
          theme={theme}
          editable={editable}
          onCommit={onCommit}
          onSelect={onSelect}
        />
      )
    case 'callout':
      return (
        <CalloutView
          block={block}
          slot={slot}
          theme={theme}
          editable={editable}
          onCommit={onCommit}
          onSelect={onSelect}
        />
      )
  }
}
