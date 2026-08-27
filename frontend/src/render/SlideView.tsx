import { iterAmbientShapes, type AmbientShape } from '@/render/ambient'
import { BlockView } from '@/render/BlockView'
import { getLayout } from '@/render/design'
import { solve, type FlexContainer } from '@/render/flexLayout'
import { iterSkinDecorations, type SkinDecoration } from '@/render/flexSkin'
import { pt, rectToStyle, resolveColor, webFontStack } from '@/render/style'
import {
  CANVAS_HEIGHT_PT,
  CANVAS_WIDTH_PT,
  type Block,
  type EditableBlockCommit,
  type Rect,
  type Slide,
  type Slot,
  type TextStyleName,
  type Theme,
} from '@/render/types'

interface SlideViewProps {
  slide: Slide
  theme: Theme
  editable?: boolean
  selectedBlockId?: string | null
  onSelectBlock?: (blockId: string | null) => void
  onCommit?: (blockId: string, body: EditableBlockCommit) => void
  /** clip=演示/缩略图裁切；reveal=编辑态溢出可见 + 分割线 */
  overflowMode?: 'clip' | 'reveal'
  /** 槽位/块 id：在其底边画溢出分割线 */
  overflowSlotIds?: ReadonlySet<string> | string[]
  /** 页序，供主题氛围层的页码水印使用 */
  slideIndex?: number
}

type PlacedEntry = { rect: Rect; text_style?: string | null }

function isFlexMode(slide: Slide): slide is Slide & { layout_tree: FlexContainer } {
  return slide.layout_mode === 'flex' && slide.layout_tree != null
}

/** flex 模式无布局槽位时，为 BlockView 构造最小伪槽（几何与 text_style 来自 solver） */
function flexPseudoSlot(block: Block, placed: PlacedEntry): Slot {
  return {
    id: block.slot_id,
    accepts: [block.type],
    rect: placed.rect,
    required: true,
    text_style: (placed.text_style ?? undefined) as TextStyleName | null | undefined,
    capacity: {},
  }
}

/**
 * 内容实占的矩形，供氛围层避让。
 *
 * 只算真正渲染出来的块（槽位空着的话那块地方就是空的），与后端
 * placed_by_block_id 同源，避让结果两端才一致。
 */
function occupiedRects(
  blocks: Block[],
  placements: Map<string, PlacedEntry> | null,
  layout: { slots: Slot[] } | null,
): Rect[] {
  return blocks
    .map((block) =>
      placements
        ? placements.get(block.id)?.rect
        : layout?.slots.find((slot) => slot.id === block.slot_id)?.rect,
    )
    .filter((rect): rect is Rect => rect != null)
}

function toIdSet(ids?: ReadonlySet<string> | string[]): Set<string> {
  if (!ids) return new Set()
  return ids instanceof Set ? ids : new Set(ids)
}

/**
 * 通用幻灯片渲染器。
 *
 * 它不认识任何具体布局，只按布局数据把内容块摆到槽位里。
 * PPTX 渲染器做的是同一件事，两端因此天然一致：
 * 新增布局只需增加一份 JSON，两端都不用改代码。
 *
 * 编辑态复用同一棵渲染树：仅把可写字段换成受约束的 contenteditable。
 * flex 模式走 layout_tree solver，跳过固定布局装饰。
 */
export function SlideView({
  slide,
  theme,
  editable = false,
  selectedBlockId = null,
  onSelectBlock,
  onCommit,
  overflowMode = 'clip',
  overflowSlotIds,
  slideIndex = 0,
}: SlideViewProps) {
  const flex = isFlexMode(slide)
  const layout = flex ? null : getLayout(slide.layout_id)
  const placements = flex
    ? new Map(solve(slide.layout_tree).map((p) => [p.block_id, p]))
    : null
  const ambient = iterAmbientShapes(
    theme,
    slide.layout_id,
    slideIndex,
    occupiedRects(slide.blocks, placements, layout),
  )
  const skinDecorations = flex ? iterSkinDecorations(slide.layout_tree) : []
  const reveal = overflowMode === 'reveal'
  const overflowIds = toIdSet(overflowSlotIds)
  const lineColor = resolveColor(theme, 'line')

  return (
    <div
      style={{
        containerType: 'size',
        position: 'relative',
        width: '100%',
        aspectRatio: `${CANVAS_WIDTH_PT} / ${CANVAS_HEIGHT_PT}`,
        background: resolveColor(theme, 'background'),
        overflow: reveal ? 'visible' : 'hidden',
      }}
      onPointerDown={(event) => {
        if (!editable || !onSelectBlock) return
        // 点在空白处（非 block）才清空选中
        if ((event.target as HTMLElement).closest('[data-block-id]')) return
        onSelectBlock(null)
      }}
    >
      <AmbientLayer shapes={ambient} theme={theme} />

      {!flex &&
        layout!.decorations.map((decoration, index) => (
          <div
            key={`${decoration.type}-${index}`}
            aria-hidden
            style={{
              ...rectToStyle(decoration.rect),
              background: resolveColor(theme, decoration.color),
            }}
          />
        ))}

      {flex &&
        skinDecorations.map((decoration, index) => (
          <SkinDecorationView
            key={`skin-${decoration.kind}-${index}`}
            decoration={decoration}
            theme={theme}
          />
        ))}

      {slide.blocks.map((block) => {
        let rect: Rect
        let slot: Slot

        if (flex && placements) {
          const placed = placements.get(block.id)
          if (!placed) return null
          rect = placed.rect
          slot = flexPseudoSlot(block, placed)
        } else {
          const found = layout!.slots.find((candidate) => candidate.id === block.slot_id)
          if (!found) return null
          slot = found
          rect = found.rect
        }

        const selected = selectedBlockId === block.id
        const selectable = Boolean(editable)
        const markOverflow =
          reveal &&
          (overflowIds.has(block.slot_id) ||
            overflowIds.has(block.id) ||
            // 无具体槽位时：任意溢出标记都画在该块（少见）
            (overflowIds.has('*') && (block.type === 'text' || block.type === 'bullets')))

        return (
          <div
            key={block.id}
            data-block-id={block.id}
            style={{
              ...rectToStyle(rect),
              overflow: reveal ? 'visible' : 'hidden',
              outline: selected
                ? `2px solid ${resolveColor(theme, 'accent')}`
                : '2px solid transparent',
              outlineOffset: selected ? '2px' : 0,
              cursor: selectable ? 'pointer' : undefined,
              zIndex: selected ? 3 : 1,
            }}
            onPointerDown={(event) => {
              if (!selectable || !onSelectBlock) return
              // 不阻断 contenteditable 的聚焦；仅同步选中
              event.stopPropagation()
              onSelectBlock(block.id)
            }}
          >
            {editable && block.locked && (
              <span
                role="img"
                title="已人工修改，AI 不会覆盖"
                aria-label="已人工修改，AI 不会覆盖"
                style={{
                  position: 'absolute',
                  top: pt(4),
                  right: pt(4),
                  zIndex: 2,
                  width: pt(6),
                  height: pt(6),
                  background: resolveColor(theme, 'accent'),
                }}
              />
            )}
            <BlockView
              block={block}
              slot={slot}
              theme={theme}
              editable={editable}
              onCommit={onCommit}
              onSelect={onSelectBlock ?? undefined}
            />
            {markOverflow && (
              <div
                aria-hidden
                data-overflow-divider="slot"
                style={{
                  position: 'absolute',
                  left: 0,
                  right: 0,
                  bottom: 0,
                  borderBottom: `1.5px dashed ${lineColor}`,
                  pointerEvents: 'none',
                  zIndex: 4,
                }}
              />
            )}
          </div>
        )
      })}

      {reveal && overflowIds.size > 0 && (
        <div
          aria-hidden
          data-overflow-divider="canvas"
          title="以下内容超出 16:9 画布"
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            top: '100%',
            marginTop: 0,
            borderTop: `1.5px dashed ${lineColor}`,
            pointerEvents: 'none',
            zIndex: 5,
          }}
        >
          <span
            style={{
              position: 'absolute',
              left: pt(8),
              top: pt(4),
              fontSize: pt(10),
              color: resolveColor(theme, 'ink_muted'),
              letterSpacing: '0.02em',
              whiteSpace: 'nowrap',
            }}
          >
            超出画布
          </span>
        </div>
      )}
    </div>
  )
}

/** 主题氛围层图元：只有矩形/椭圆/文本三种，与 PPTX 导出一一对应 */
/**
 * 氛围层单独套一层裁切容器。
 *
 * 装饰是有意出血的（同心光晕靠画布边缘裁才不会被压成月牙），但编辑态外层
 * 开着 overflow: visible 给内容溢出让路，装饰不能跟着漏到画布外面去。
 */
function AmbientLayer({ shapes, theme }: { shapes: AmbientShape[]; theme: Theme }) {
  if (!shapes.length) return null
  return (
    <div aria-hidden style={{ position: 'absolute', inset: 0, overflow: 'hidden', zIndex: 0 }}>
      {shapes.map((shape, index) => (
        <AmbientShapeView key={`ambient-${index}`} shape={shape} theme={theme} />
      ))}
    </div>
  )
}

function AmbientShapeView({ shape, theme }: { shape: AmbientShape; theme: Theme }) {
  const base = {
    ...rectToStyle(shape.rect),
    zIndex: 0,
    pointerEvents: 'none',
  } as const

  if (shape.kind !== 'text') {
    return (
      <div
        aria-hidden
        style={{
          ...base,
          background: shape.color,
          borderRadius: shape.kind === 'ellipse' ? '50%' : undefined,
        }}
      />
    )
  }

  const family = shape.font === 'body' ? theme.fonts.body : theme.fonts.display
  return (
    <div
      aria-hidden
      style={{
        ...base,
        display: 'flex',
        alignItems: 'center',
        justifyContent:
          shape.align === 'center' ? 'center' : shape.align === 'right' ? 'flex-end' : 'flex-start',
        fontFamily: webFontStack(family),
        fontSize: pt(shape.size_pt ?? 0),
        fontWeight: shape.weight ?? 400,
        letterSpacing: shape.letter_spacing_pt ? pt(shape.letter_spacing_pt) : undefined,
        lineHeight: 1,
        color: shape.color,
        whiteSpace: 'nowrap',
      }}
    >
      {shape.text}
    </div>
  )
}

function SkinDecorationView({
  decoration,
  theme,
}: {
  decoration: SkinDecoration
  theme: Theme
}) {
  const color = resolveColor(theme, decoration.color_token)
  const base = rectToStyle(decoration.rect)

  if (decoration.kind === 'fill_box') {
    return (
      <div
        aria-hidden
        style={{
          ...base,
          background: color,
          borderRadius: pt(decoration.radius_pt ?? 0),
          zIndex: 0,
          pointerEvents: 'none',
        }}
      />
    )
  }

  if (decoration.kind === 'outline_box') {
    return (
      <div
        aria-hidden
        style={{
          ...base,
          border: `${pt(1.5)} solid ${color}`,
          borderRadius: pt(decoration.radius_pt ?? 0),
          boxSizing: 'border-box',
          zIndex: 0,
          pointerEvents: 'none',
        }}
      />
    )
  }

  if (decoration.kind === 'side_line' || decoration.kind === 'timeline_axis') {
    return (
      <div
        aria-hidden
        style={{
          ...base,
          background: color,
          zIndex: 0,
          pointerEvents: 'none',
        }}
      />
    )
  }

  if (decoration.kind === 'timeline_dot') {
    return (
      <div
        aria-hidden
        style={{
          ...base,
          background: color,
          borderRadius: '50%',
          zIndex: 0,
          pointerEvents: 'none',
        }}
      />
    )
  }

  return (
    <div
      aria-hidden
      style={{
        ...base,
        background: color,
        borderRadius: '50%',
        display: 'grid',
        placeItems: 'center',
        color: resolveColor(theme, 'background'),
        fontSize: pt(11),
        fontWeight: 700,
        lineHeight: 1,
        zIndex: 0,
        pointerEvents: 'none',
      }}
    >
      {decoration.text}
    </div>
  )
}

/** 缩略图：与正式渲染共用同一组件，只是容器更小 */
export function SlideThumbnail({ slide, theme, slideIndex }: SlideViewProps) {
  return (
    <div style={{ border: `1px solid ${resolveColor(theme, 'line')}`, padding: pt(0) }}>
      <SlideView slide={slide} theme={theme} slideIndex={slideIndex} overflowMode="clip" />
    </div>
  )
}
