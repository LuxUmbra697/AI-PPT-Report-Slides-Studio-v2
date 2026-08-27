import { API_PREFIX } from '@/api/client'
import { tokenStore } from '@/features/auth/token'

/**
 * 读取一条 SSE 流直到结束或被取消。
 *
 * 没有用浏览器内置的 EventSource：它不支持自定义请求头，
 * 而接口鉴权走的是 Authorization Bearer。
 */
export async function consumeEventStream<T>(
  path: string,
  signal: AbortSignal,
  onEvent: (event: T) => void,
) {
  const token = tokenStore.get()
  const response = await fetch(`${API_PREFIX}${path}`, {
    headers: {
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    signal,
  })
  if (!response.ok || !response.body) {
    throw new Error(`SSE connection failed: ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (!signal.aborted) {
    const { done, value } = await reader.read()
    if (done) return
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')

    let boundary = buffer.indexOf('\n\n')
    while (boundary >= 0) {
      const frame = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      const data = frame
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trimStart())
        .join('\n')
      if (data) onEvent(JSON.parse(data) as T)
      boundary = buffer.indexOf('\n\n')
    }
  }
}

export function delay(milliseconds: number, signal: AbortSignal) {
  return new Promise<void>((resolve) => {
    if (signal.aborted) {
      resolve()
      return
    }
    const timer = window.setTimeout(resolve, milliseconds)
    signal.addEventListener(
      'abort',
      () => {
        window.clearTimeout(timer)
        resolve()
      },
      { once: true },
    )
  })
}
