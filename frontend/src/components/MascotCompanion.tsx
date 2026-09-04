import { GripHorizontal, MessageCircleMore, RotateCcw, Sparkles } from 'lucide-react'
import { type CSSProperties, type PointerEvent, useEffect, useRef, useState } from 'react'
import { useUiTheme } from '@/features/ui/useUiTheme'
import { getUiTheme, type UiThemeId } from '@/features/ui/uiThemes'

type Position = { x: number; y: number }
type MascotAction = 'wave' | 'jump' | 'magic' | 'surprise'

const STORAGE_KEY = 'luxumbra-mascot-position-v2'
const MASCOT_WIDTH = 176
const MASCOT_HEIGHT = 236

const ACTIONS: Record<MascotAction, number[]> = {
  wave: [2, 1, 2, 0],
  jump: [0, 3, 3, 1, 0],
  magic: [0, 4, 4, 2, 0],
  surprise: [5, 5, 1, 0],
}

const DIALOGUES: Record<UiThemeId, string[]> = {
  sakura: ['灵感正在发芽呢！', '要不要试试魔法樱语封面？', '点子再小，也值得闪闪发光。', '锵锵——排版魔法完成！'],
  neon: ['信号满格，创作频道接通！', '检测到一个超酷的标题。', '数据流正常，继续向前！', '让我给这页加一点霓虹能量。'],
  shrine: ['今天也要写出好故事呀。', '樱签说：这一页会很顺利。', '留白也是一种呼吸。', '愿灵感如花瓣落在你手心。'],
  celestial: ['星图显示：灵感就在下一页。', '把复杂的事讲清楚，很浪漫。', '书页翻动时，故事就开始了。', '要一起去找最亮的重点吗？'],
  foxfire: ['狐火已经替你照亮重点啦！', '漂亮的开场，要像烟火一样。', '别怕改稿，好作品都爱变身。', '哼哼，这页交给我来点亮！'],
}

function clampPosition(position: Position): Position {
  return {
    x: Math.min(Math.max(8, position.x), Math.max(8, window.innerWidth - MASCOT_WIDTH - 8)),
    y: Math.min(Math.max(8, position.y), Math.max(8, window.innerHeight - MASCOT_HEIGHT - 8)),
  }
}

function defaultPosition(): Position {
  return {
    x: Math.max(8, window.innerWidth - MASCOT_WIDTH - 22),
    y: Math.max(8, window.innerHeight - MASCOT_HEIGHT - 20),
  }
}

function initialPosition(): Position {
  try {
    const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? '') as Position
    return clampPosition(saved)
  } catch {
    return defaultPosition()
  }
}

function frameStyle(asset: string, frame: number): CSSProperties {
  const column = frame % 3
  const row = Math.floor(frame / 3)
  return {
    backgroundImage: `url('${asset}')`,
    '--mascot-frame-x': `${column * 50}%`,
    '--mascot-frame-y': `${row * 100}%`,
  } as CSSProperties
}

/** 六帧角色播放器：待机眨眼，点击播放动作，拖动位置会保存到本地。 */
export function MascotCompanion() {
  const { themeId } = useUiTheme()
  const theme = getUiTheme(themeId)
  const [position, setPosition] = useState<Position>(initialPosition)
  const positionRef = useRef(position)
  const [dragging, setDragging] = useState(false)
  const [frame, setFrame] = useState(0)
  const [action, setAction] = useState<MascotAction | null>(null)
  const [line, setLine] = useState(`我是 ${theme.mascotName}，点我会有不同动作哦！`)
  const [burst, setBurst] = useState(0)
  const grabRef = useRef<Position | null>(null)
  const pointerStartRef = useRef<Position | null>(null)
  const movedRef = useRef(false)
  const actionIndexRef = useRef(0)

  const updatePosition = (next: Position) => {
    positionRef.current = next
    setPosition(next)
  }

  useEffect(() => {
    setLine(`我是 ${theme.mascotName}，点我会有不同动作哦！`)
    setFrame(0)
    setAction(null)
  }, [theme.mascotName])

  useEffect(() => {
    if (action) return
    const timer = window.setInterval(() => setFrame((current) => (current === 0 ? 1 : 0)), 780)
    return () => window.clearInterval(timer)
  }, [action])

  useEffect(() => {
    if (!action) return
    const sequence = ACTIONS[action]
    let index = 0
    setFrame(sequence[0])
    const timer = window.setInterval(() => {
      index += 1
      if (index >= sequence.length) {
        window.clearInterval(timer)
        setAction(null)
        setFrame(0)
        return
      }
      setFrame(sequence[index])
    }, 190)
    return () => window.clearInterval(timer)
  }, [action])

  useEffect(() => {
    const reposition = () => {
      const next = clampPosition(positionRef.current)
      positionRef.current = next
      setPosition(next)
    }
    window.addEventListener('resize', reposition)
    return () => window.removeEventListener('resize', reposition)
  }, [])

  const playNextAction = () => {
    const actionNames = Object.keys(ACTIONS) as MascotAction[]
    const nextAction = actionNames[actionIndexRef.current % actionNames.length]
    const lines = DIALOGUES[themeId]
    setLine(lines[actionIndexRef.current % lines.length])
    actionIndexRef.current += 1
    setBurst((value) => value + 1)
    setAction(nextAction)
  }

  const move = (event: PointerEvent<HTMLDivElement>) => {
    const grab = grabRef.current
    const start = pointerStartRef.current
    if (!grab || !start) return
    if (Math.hypot(event.clientX - start.x, event.clientY - start.y) > 5) movedRef.current = true
    updatePosition(clampPosition({ x: event.clientX - grab.x, y: event.clientY - grab.y }))
  }

  const stop = () => {
    grabRef.current = null
    pointerStartRef.current = null
    setDragging(false)
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(positionRef.current))
  }

  return (
    <div
      className={`mascot-companion mascot-${themeId}${dragging ? ' is-dragging' : ''}${action ? ` is-${action}` : ''}`}
      style={{ transform: `translate3d(${position.x}px, ${position.y}px, 0)` }}
      onPointerMove={move}
      onPointerUp={stop}
      onPointerCancel={stop}
    >
      <div className="mascot-bubble" role="status" aria-live="polite">
        <span><MessageCircleMore className="size-3" /> {theme.mascotName}</span>
        <small>{line}</small>
      </div>

      <div
        className="mascot-art"
        style={frameStyle(theme.mascotAsset, frame)}
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId)
          grabRef.current = { x: event.clientX - position.x, y: event.clientY - position.y }
          pointerStartRef.current = { x: event.clientX, y: event.clientY }
          movedRef.current = false
          setDragging(true)
        }}
        onClick={() => {
          if (movedRef.current) return
          playNextAction()
        }}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            playNextAction()
          }
        }}
        aria-label={`${theme.mascotName}看板娘，点击互动，按住拖动`}
        role="button"
        tabIndex={0}
      >
        <span className="mascot-grip"><GripHorizontal className="size-3.5" /></span>
      </div>

      <div key={burst} className="mascot-action-burst" aria-hidden>
        <Sparkles /><i /><i /><i /><i />
      </div>

      <button
        type="button"
        className="mascot-reset"
        aria-label="重置看板娘位置"
        onClick={() => {
          const next = defaultPosition()
          updatePosition(next)
          window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
        }}
      >
        <RotateCcw className="size-3" />
      </button>
    </div>
  )
}
