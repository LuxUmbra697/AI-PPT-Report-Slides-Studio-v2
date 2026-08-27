import {
  type CSSProperties,
  type ClipboardEvent,
  type KeyboardEvent,
  useEffect,
  useLayoutEffect,
  useRef,
} from 'react'
import { cn } from '@/lib/utils'

const SAVE_IDLE_MS = 800

interface EditableTextProps {
  value: string
  ariaLabel: string
  /** false 时 Enter 提交并失焦，不插入换行 */
  multiline?: boolean
  style?: CSSProperties
  className?: string
  onCommit: (next: string) => void
  onFocus?: () => void
  /** 有回调时 Enter 先提交再回调，不再失焦（列表增项） */
  onEnter?: () => void
  /** 内容为空时按 Backspace 回调（列表删项） */
  onBackspaceWhenEmpty?: () => void
  /** 变化时强制聚焦；用于插入/删除后跳到目标项 */
  focusToken?: number | null
  /** 配合 focusToken：落在开头或末尾 */
  focusCaret?: 'start' | 'end'
}

/** 两串公共前缀长度：撤销删除 / 重做插入时把光标落在变化处 */
function caretAtChange(from: string, to: string): number {
  const limit = Math.min(from.length, to.length)
  let i = 0
  while (i < limit && from[i] === to[i]) i += 1
  return i
}

function placeCaret(el: HTMLElement, offset: number) {
  const selection = window.getSelection()
  if (!selection) return

  if (document.activeElement !== el) {
    el.focus()
  }

  const range = document.createRange()
  const textNode = el.firstChild
  if (textNode && textNode.nodeType === Node.TEXT_NODE) {
    const length = textNode.textContent?.length ?? 0
    const next = Math.max(0, Math.min(offset, length))
    range.setStart(textNode, next)
    range.collapse(true)
  } else if (offset <= 0) {
    range.setStart(el, 0)
    range.collapse(true)
  } else {
    range.selectNodeContents(el)
    range.collapse(false)
  }

  selection.removeAllRanges()
  selection.addRange(range)
}

/**
 * 受约束的 contenteditable：纯文本、主题样式原样继承，
 * 停止输入后自动提交，失焦立即提交，无变化不回调。
 *
 * 不用 React children 驱动文本，避免重渲染冲掉光标与草稿。
 */
export function EditableText({
  value,
  ariaLabel,
  multiline = false,
  style,
  className,
  onCommit,
  onFocus,
  onEnter,
  onBackspaceWhenEmpty,
  focusToken = null,
  focusCaret = 'start',
}: EditableTextProps) {
  const ref = useRef<HTMLSpanElement>(null)
  const focusedRef = useRef(false)
  const valueRef = useRef(value)
  const draftRef = useRef(value)
  /** 刚用 ⌘Z 丢掉的未提交草稿，供 ⌘⇧Z 就地重做 */
  const pendingRedoRef = useRef<string | null>(null)
  const timerRef = useRef<number | null>(null)
  const onCommitRef = useRef(onCommit)
  onCommitRef.current = onCommit
  const onEnterRef = useRef(onEnter)
  onEnterRef.current = onEnter
  const onBackspaceWhenEmptyRef = useRef(onBackspaceWhenEmpty)
  onBackspaceWhenEmptyRef.current = onBackspaceWhenEmpty
  const lastFocusTokenRef = useRef<number | null>(null)

  const clearTimer = () => {
    if (timerRef.current != null) {
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }

  const commitIfChanged = () => {
    const next = draftRef.current
    if (next === valueRef.current) return
    pendingRedoRef.current = null
    onCommitRef.current(next)
  }

  const scheduleCommit = () => {
    clearTimer()
    timerRef.current = window.setTimeout(() => {
      timerRef.current = null
      commitIfChanged()
    }, SAVE_IDLE_MS)
  }

  const syncDom = (next: string, caretFrom?: string) => {
    const el = ref.current
    if (!el) return
    const from = caretFrom ?? el.textContent ?? draftRef.current
    if (el.textContent !== next) {
      el.textContent = next
    }
    draftRef.current = next

    // native focus / 重渲染后 focusedRef 可能短暂不同步，以 activeElement 为准
    const alive = focusedRef.current || document.activeElement === el
    if (!alive) return

    focusedRef.current = true
    const caret = caretAtChange(from, next)
    placeCaret(el, caret)
    // 部分浏览器会在 keydown 收尾把光标打回开头，下一帧再钉一次
    requestAnimationFrame(() => {
      if (ref.current !== el) return
      if (!focusedRef.current && document.activeElement !== el) return
      placeCaret(el, caret)
    })
  }

  useLayoutEffect(() => {
    const previous = valueRef.current
    valueRef.current = value
    if (!ref.current) return
    if (ref.current.textContent === value) {
      draftRef.current = value
      return
    }
    // 外部更新（撤销/AI 写回）时，即便仍聚焦也要同步 DOM，并尽量保住光标落点
    if (!focusedRef.current || previous !== value) {
      syncDom(value, previous)
    }
  }, [value])

  useLayoutEffect(() => {
    if (focusToken == null || focusToken === lastFocusTokenRef.current) return
    lastFocusTokenRef.current = focusToken
    const el = ref.current
    if (!el) return
    focusedRef.current = true
    el.focus()
    const offset = focusCaret === 'end' ? (el.textContent?.length ?? 0) : 0
    placeCaret(el, offset)
    requestAnimationFrame(() => {
      if (ref.current !== el) return
      placeCaret(el, offset)
    })
  }, [focusToken, focusCaret])

  useEffect(() => () => clearTimer(), [])

  const onPaste = (event: ClipboardEvent<HTMLSpanElement>) => {
    event.preventDefault()
    const text = event.clipboardData.getData('text/plain')
    const normalized = multiline ? text : text.replace(/[\r\n]+/g, ' ')
    document.execCommand('insertText', false, normalized)
  }

  const onKeyDown = (event: KeyboardEvent<HTMLSpanElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      event.stopPropagation()
      clearTimer()
      pendingRedoRef.current = null
      syncDom(valueRef.current)
      ref.current?.blur()
      return
    }

    const mod = event.metaKey || event.ctrlKey
    if (mod && event.key.toLowerCase() === 'z') {
      // 未提交草稿：⌘Z 就地还原，并缓存以便 ⌘⇧Z 重做
      if (!event.shiftKey && draftRef.current !== valueRef.current) {
        event.preventDefault()
        event.stopPropagation()
        clearTimer()
        const discarded = draftRef.current
        pendingRedoRef.current = discarded
        syncDom(valueRef.current, discarded)
        return
      }

      // 刚丢掉的未提交草稿：⌘⇧Z / ⌘Y 就地重做，不落到页面历史栈
      if (
        event.shiftKey &&
        pendingRedoRef.current != null &&
        draftRef.current === valueRef.current
      ) {
        event.preventDefault()
        event.stopPropagation()
        const redoText = pendingRedoRef.current
        pendingRedoRef.current = null
        syncDom(redoText, valueRef.current)
        scheduleCommit()
        return
      }

      // 已提交：挡住浏览器自带撤销，放行到页面级历史栈
      event.preventDefault()
      return
    }

    if (mod && event.key.toLowerCase() === 'y') {
      if (
        pendingRedoRef.current != null &&
        draftRef.current === valueRef.current
      ) {
        event.preventDefault()
        event.stopPropagation()
        const redoText = pendingRedoRef.current
        pendingRedoRef.current = null
        syncDom(redoText, valueRef.current)
        scheduleCommit()
        return
      }
      event.preventDefault()
      return
    }

    if (!multiline && event.key === 'Enter') {
      event.preventDefault()
      clearTimer()
      commitIfChanged()
      if (onEnterRef.current) {
        onEnterRef.current()
        return
      }
      ref.current?.blur()
      return
    }

    if (
      !multiline &&
      event.key === 'Backspace' &&
      onBackspaceWhenEmptyRef.current &&
      draftRef.current.length === 0
    ) {
      event.preventDefault()
      clearTimer()
      onBackspaceWhenEmptyRef.current()
    }
  }

  return (
    <span
      ref={ref}
      role="textbox"
      aria-label={ariaLabel}
      aria-multiline={multiline || undefined}
      contentEditable="plaintext-only"
      suppressContentEditableWarning
      className={cn(
        // 透明描边占位，避免 focus 时布局跳动；颜色跟当前文字走，不引入额外主题色块
        'shadow-[inset_0_0_0_1px_transparent]',
        'hover:shadow-[inset_0_0_0_1px_color-mix(in_oklab,currentColor_22%,transparent)]',
        'focus:shadow-[inset_0_0_0_1px_color-mix(in_oklab,currentColor_40%,transparent)]',
        className,
      )}
      style={{
        ...style,
        outline: 'none',
        cursor: 'text',
        borderRadius: 0,
        minWidth: '0.5em',
        // 单行用 inline，避免表格单元格 / KPI 数值被 inline-block 撑成独立块导致跳动
        display: multiline ? 'block' : 'inline',
        whiteSpace: multiline ? 'pre-wrap' : undefined,
        wordBreak: multiline ? 'break-word' : undefined,
      }}
      onFocus={() => {
        focusedRef.current = true
        onFocus?.()
      }}
      onBlur={() => {
        focusedRef.current = false
        pendingRedoRef.current = null
        clearTimer()
        commitIfChanged()
      }}
      onInput={() => {
        draftRef.current = ref.current?.textContent ?? ''
        pendingRedoRef.current = null
        scheduleCommit()
      }}
      onPaste={onPaste}
      onKeyDown={onKeyDown}
    />
  )
}
