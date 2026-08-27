import { ChevronLeft, ChevronRight, Maximize2, Minimize2, X } from 'lucide-react'
import { type ReactNode, useCallback, useEffect, useRef, useState } from 'react'
import { type DeckSlide, toRenderSlide } from '@/features/deck/types'
import { cn } from '@/lib/utils'
import { SlideView } from '@/render/SlideView'
import { CANVAS_HEIGHT_PT, CANVAS_WIDTH_PT, type Theme } from '@/render/types'

const CHROME_IDLE_MS = 2200
const TIP_MS = 3200
const ASPECT = CANVAS_WIDTH_PT / CANVAS_HEIGHT_PT

/**
 * 演示放映：全幅 16:9 铺满视口、控件闲置隐藏、底部分段进度、点击左右翻页。
 * 不含演讲者备注 / 聚光灯 / 分享链接。
 */
export function PresentMode({
  slides,
  theme,
  startIndex,
  onClose,
}: {
  slides: DeckSlide[]
  theme: Theme
  startIndex: number
  onClose: () => void
}) {
  const [index, setIndex] = useState(startIndex)
  const [chromeVisible, setChromeVisible] = useState(true)
  const [tipVisible, setTipVisible] = useState(true)
  const [idleCursor, setIdleCursor] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const chromeTimerRef = useRef<number | null>(null)
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  const last = Math.max(slides.length - 1, 0)
  const clamp = useCallback(
    (next: number) => Math.min(Math.max(next, 0), last),
    [last],
  )
  const go = useCallback((target: number) => setIndex(clamp(target)), [clamp])
  const prev = useCallback(() => setIndex((current) => Math.max(current - 1, 0)), [])
  const next = useCallback(
    () => setIndex((current) => Math.min(current + 1, last)),
    [last],
  )

  const bumpChrome = useCallback(() => {
    setChromeVisible(true)
    setIdleCursor(false)
    if (chromeTimerRef.current != null) window.clearTimeout(chromeTimerRef.current)
    chromeTimerRef.current = window.setTimeout(() => {
      setChromeVisible(false)
      setIdleCursor(true)
      chromeTimerRef.current = null
    }, CHROME_IDLE_MS)
  }, [])

  const toggleFullscreen = useCallback(async () => {
    const root = rootRef.current
    if (!root) return
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen()
      } else {
        await root.requestFullscreen()
      }
    } catch {
      // 浏览器拒绝全屏时仍可覆盖层放映
    }
  }, [])

  useEffect(() => {
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    bumpChrome()
    const tipTimer = window.setTimeout(() => setTipVisible(false), TIP_MS)

    const onFullscreenChange = () => {
      setIsFullscreen(Boolean(document.fullscreenElement))
    }
    document.addEventListener('fullscreenchange', onFullscreenChange)

    const onKeyDown = (event: KeyboardEvent) => {
      bumpChrome()
      if (event.key === 'ArrowRight' || event.key === ' ' || event.key === 'PageDown') {
        event.preventDefault()
        setIndex((current) => Math.min(current + 1, last))
      } else if (event.key === 'ArrowLeft' || event.key === 'PageUp') {
        event.preventDefault()
        setIndex((current) => Math.max(current - 1, 0))
      } else if (event.key === 'Home') {
        event.preventDefault()
        setIndex(0)
      } else if (event.key === 'End') {
        event.preventDefault()
        setIndex(last)
      } else if (event.key === 'f' || event.key === 'F') {
        event.preventDefault()
        void toggleFullscreen()
      } else if (event.key === 'Escape') {
        // 全屏时 Esc 先退浏览器全屏；仅非全屏时退出演示
        if (document.fullscreenElement) return
        onCloseRef.current()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('fullscreenchange', onFullscreenChange)
      window.clearTimeout(tipTimer)
      if (chromeTimerRef.current != null) window.clearTimeout(chromeTimerRef.current)
      if (document.fullscreenElement) void document.exitFullscreen().catch(() => {})
    }
  }, [bumpChrome, last, toggleFullscreen])

  const slide = slides[clamp(index)]
  if (!slide) return null

  return (
    <div
      ref={rootRef}
      role="dialog"
      aria-modal="true"
      aria-label="演示放映"
      className={cn(
        'fixed inset-0 z-[60] bg-black text-white',
        idleCursor && !chromeVisible ? 'cursor-none' : 'cursor-default',
      )}
      onMouseMove={bumpChrome}
      onPointerDown={bumpChrome}
    >
      <div className="absolute inset-0 grid place-items-center overflow-hidden">
        <div
          key={slide.id}
          className="present-slide-in overflow-hidden shadow-[0_0_0_1px_rgba(255,255,255,0.04)]"
          style={{
            width: `min(100vw, calc(100vh * ${ASPECT}))`,
            height: `min(100vh, calc(100vw / ${ASPECT}))`,
          }}
        >
          <SlideView slide={toRenderSlide(slide)} theme={theme} slideIndex={clamp(index)} />
        </div>
      </div>

      {/* 左右热区翻页；z-index 低于顶栏/底栏，避免抢走控件点击 */}
      <button
        type="button"
        aria-label="上一页"
        disabled={index === 0}
        className="absolute inset-y-0 left-0 z-[1] w-[28%] cursor-w-resize border-0 bg-transparent disabled:cursor-default"
        onClick={(event) => {
          event.stopPropagation()
          prev()
        }}
      />
      <button
        type="button"
        aria-label="下一页"
        disabled={index >= last}
        className="absolute inset-y-0 right-0 z-[1] w-[72%] cursor-e-resize border-0 bg-transparent disabled:cursor-default"
        onClick={(event) => {
          event.stopPropagation()
          next()
        }}
      />

      <div
        className={cn(
          'pointer-events-none absolute top-5 right-5 z-[3] rounded-md bg-black/70 px-3 py-1.5 text-[12px] text-white/90 shadow-pop backdrop-blur-sm transition-opacity duration-500',
          tipVisible ? 'opacity-100' : 'opacity-0',
        )}
      >
        退出演示 Esc
      </div>

      <div
        className={cn(
          'absolute inset-x-0 top-0 z-[3] flex items-start justify-end gap-1 bg-gradient-to-b from-black/55 to-transparent px-4 pt-3 pb-10 transition-opacity duration-300',
          chromeVisible ? 'opacity-100' : 'pointer-events-none opacity-0',
        )}
      >
        <ChromeIconButton
          label={isFullscreen ? '退出全屏' : '进入全屏'}
          onClick={() => void toggleFullscreen()}
        >
          {isFullscreen ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
        </ChromeIconButton>
        <ChromeIconButton label="退出放映" onClick={onClose}>
          <X className="size-4" />
        </ChromeIconButton>
      </div>

      <div
        className={cn(
          'absolute inset-x-0 bottom-0 z-[3] bg-gradient-to-t from-black/60 to-transparent px-5 pt-10 pb-4 transition-opacity duration-300',
          chromeVisible ? 'opacity-100' : 'pointer-events-none opacity-0',
        )}
      >
        <div className="mx-auto flex max-w-5xl items-center gap-3">
          <ChromeIconButton label="上一页" disabled={index === 0} onClick={prev}>
            <ChevronLeft className="size-4" />
          </ChromeIconButton>

          <span className="min-w-14 text-center text-[12px] tabular-nums tracking-wide text-white/75">
            {String(index + 1).padStart(2, '0')} / {String(slides.length).padStart(2, '0')}
          </span>

          <ChromeIconButton label="下一页" disabled={index >= last} onClick={next}>
            <ChevronRight className="size-4" />
          </ChromeIconButton>

          <div
            className="ml-2 flex min-w-0 flex-1 items-center gap-1"
            role="navigation"
            aria-label="演示进度"
          >
            {slides.map((item, i) => (
              <button
                key={item.id}
                type="button"
                aria-label={`第 ${i + 1} 页`}
                aria-current={i === index ? 'true' : undefined}
                onClick={() => go(i)}
                className={cn(
                  'h-1 min-w-0 flex-1 rounded-full transition-colors',
                  i === index
                    ? 'bg-white'
                    : i < index
                      ? 'bg-white/55 hover:bg-white/75'
                      : 'bg-white/20 hover:bg-white/40',
                )}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function ChromeIconButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string
  disabled?: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      onClick={(event) => {
        event.stopPropagation()
        onClick()
      }}
      className="grid size-9 place-items-center rounded-full text-white/80 transition-colors hover:bg-white/12 hover:text-white disabled:pointer-events-none disabled:opacity-30"
    >
      {children}
    </button>
  )
}
