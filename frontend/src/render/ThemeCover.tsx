import { iterAmbientShapes, type AmbientShape } from '@/render/ambient'
import type { CSSProperties } from 'react'
import { resolveColor, textStyleToCss, webFontStack } from '@/render/style'
import { CANVAS_HEIGHT_PT, CANVAS_WIDTH_PT, type Theme } from '@/render/types'

type CoverVariant = NonNullable<Theme['visual']>['cover_variant']

const VARIANT_LAYOUT: Record<CoverVariant, {
  align: 'left' | 'center'
  justify: 'center' | 'flex-end'
  padding: string
  titleWidth: string
}> = {
  editorial: { align: 'left', justify: 'center', padding: '8% 10%', titleWidth: '70%' },
  split: { align: 'left', justify: 'center', padding: '8% 43% 8% 9%', titleWidth: '100%' },
  poster: { align: 'left', justify: 'flex-end', padding: '8% 10% 10%', titleWidth: '76%' },
  framed: { align: 'center', justify: 'center', padding: '12% 18%', titleWidth: '100%' },
  spotlight: { align: 'left', justify: 'center', padding: '8% 36% 8% 9%', titleWidth: '100%' },
  ribbon: { align: 'left', justify: 'flex-end', padding: '8% 36% 11% 9%', titleWidth: '100%' },
}

function shapeStyle(shape: AmbientShape): CSSProperties {
  return {
    position: 'absolute',
    left: `${shape.rect.x * 100}%`,
    top: `${shape.rect.y * 100}%`,
    width: `${shape.rect.w * 100}%`,
    height: `${shape.rect.h * 100}%`,
    transform: shape.rotation ? `rotate(${shape.rotation}deg)` : undefined,
    transformOrigin: 'center',
    background: shape.kind === 'text' ? undefined : shape.color,
    borderRadius: shape.kind === 'ellipse' ? '50%' : shape.kind === 'round_rect' ? '12cqw' : undefined,
    color: shape.color,
    display: shape.kind === 'text' ? 'flex' : undefined,
    alignItems: shape.kind === 'text' ? 'center' : undefined,
    justifyContent:
      shape.kind === 'text'
        ? shape.align === 'right'
          ? 'flex-end'
          : shape.align === 'center'
            ? 'center'
            : 'flex-start'
        : undefined,
  }
}

/** 主题封面缩略图直接渲染模板图元与构图变体，所见即导出结果。 */
export function ThemeCover({ theme, title }: { theme: Theme; title: string }) {
  const display = textStyleToCss(theme, 'title')
  const caption = textStyleToCss(theme, 'caption')
  const variant = theme.visual?.cover_variant ?? 'editorial'
  const layout = VARIANT_LAYOUT[variant]
  const ambient = iterAmbientShapes(theme, 'cover', 0)

  return (
    <div
      style={{
        containerType: 'size',
        position: 'relative',
        width: '100%',
        aspectRatio: `${CANVAS_WIDTH_PT} / ${CANVAS_HEIGHT_PT}`,
        background: resolveColor(theme, 'background'),
        overflow: 'hidden',
      }}
    >
      {ambient.map((shape, index) => (
        <span
          key={`${shape.kind}-${index}`}
          aria-hidden
          style={{
            ...shapeStyle(shape),
            fontFamily:
              shape.kind === 'text'
                ? webFontStack(shape.font === 'body' ? theme.fonts.body : theme.fonts.display)
                : undefined,
            fontSize: shape.kind === 'text' ? `${(shape.size_pt ?? 10) * 0.075}cqw` : undefined,
            fontWeight: shape.weight,
            whiteSpace: 'nowrap',
          }}
        >
          {shape.kind === 'text' ? shape.text : null}
        </span>
      ))}

      <div
        style={{
          position: 'absolute',
          inset: 0,
          zIndex: 2,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: layout.justify,
          alignItems: layout.align === 'center' ? 'center' : 'flex-start',
          gap: '3.2cqh',
          padding: layout.padding,
          textAlign: layout.align,
        }}
      >
        <span style={{ ...caption, fontSize: '3.1cqw', letterSpacing: '0.18em' }}>
          {theme.name}
        </span>
        <span
          style={{
            ...display,
            width: layout.titleWidth,
            fontSize: variant === 'poster' ? '10.2cqw' : '8.5cqw',
            lineHeight: 1.14,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {title}
        </span>
        <span
          aria-hidden
          style={{
            border: `1px solid ${resolveColor(theme, 'line_strong')}`,
            borderRadius: '999px',
            padding: '1.2cqh 2.1cqw',
            color: resolveColor(theme, 'ink_muted'),
            background: resolveColor(theme, 'surface'),
            fontSize: '2.7cqw',
            fontWeight: 700,
          }}
        >
          {theme.visual?.content_variant ?? 'clean'} · {theme.visual?.transition ?? 'fade'}
        </span>
      </div>
    </div>
  )
}
