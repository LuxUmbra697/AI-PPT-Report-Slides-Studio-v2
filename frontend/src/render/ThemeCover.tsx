import { resolveColor, textStyleToCss } from '@/render/style'
import { CANVAS_HEIGHT_PT, CANVAS_WIDTH_PT, type Theme } from '@/render/types'

/**
 * 主题封面：用主题自身的调色板与字体画一张 16:9 缩略卡。
 *
 * 选主题时用户要看到的是"成品长什么气质"，而不是主题名字，
 * 因此这里刻意复用渲染层的令牌解析，保证与真实页面同源。
 */
export function ThemeCover({ theme, title }: { theme: Theme; title: string }) {
  const display = textStyleToCss(theme, 'title')
  const caption = textStyleToCss(theme, 'caption')

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
      <div
        aria-hidden
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          bottom: 0,
          width: '2.2%',
          background: resolveColor(theme, 'accent'),
        }}
      />
      <div
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          gap: '4cqh',
          padding: '8% 9% 8% 12%',
        }}
      >
        <span style={{ ...caption, fontSize: '3.4cqw', letterSpacing: '0.18em' }}>
          {theme.name}
        </span>
        <span
          style={{
            ...display,
            fontSize: '9cqw',
            lineHeight: 1.2,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {title}
        </span>
        <div aria-hidden style={{ display: 'flex', flexDirection: 'column', gap: '2.4cqh' }}>
          {[86, 64].map((width) => (
            <span
              key={width}
              style={{
                width: `${width}%`,
                height: '1.6cqh',
                background: resolveColor(theme, 'line_strong'),
                opacity: 0.7,
              }}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
