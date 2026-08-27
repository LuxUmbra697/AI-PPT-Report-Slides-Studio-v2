import { useEffect, useRef, useState } from 'react'
import { consumeEventStream, delay } from '@/lib/sse'

const RECONNECT_DELAY_MS = 1_000

interface Options<T> {
  path: string
  active: boolean
  /** 收到这些事件类型后停止重连：任务已经有终态，再连只会空转 */
  terminalTypes: readonly string[]
  onEvent?: (event: T) => void
}

/**
 * 订阅一条服务端事件流，断线后自动重连。
 *
 * 服务端每条事件都带完整状态，因此重连不需要补发历史：
 * 拿到的第一帧就是当前快照。
 */
export function useEventStream<T extends { type: string }>({
  path,
  active,
  terminalTypes,
  onEvent,
}: Options<T>) {
  const [event, setEvent] = useState<T | null>(null)
  const [connectionError, setConnectionError] = useState(false)
  // 回调每次渲染都是新引用，放进依赖会让连接不断重建
  const handlerRef = useRef(onEvent)
  handlerRef.current = onEvent

  useEffect(() => {
    if (!active) {
      setConnectionError(false)
      return
    }

    const controller = new AbortController()

    const connect = async () => {
      while (!controller.signal.aborted) {
        let finished = false
        try {
          await consumeEventStream<T>(path, controller.signal, (next) => {
            setEvent(next)
            setConnectionError(false)
            handlerRef.current?.(next)
            if (terminalTypes.includes(next.type)) finished = true
          })
        } catch {
          if (controller.signal.aborted) return
          setConnectionError(true)
        }
        if (finished) return
        await delay(RECONNECT_DELAY_MS, controller.signal)
      }
    }

    void connect()
    return () => controller.abort()
    // terminalTypes 是模块级常量数组，不参与依赖比较
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, path])

  return { event, connectionError }
}
