import { tokenStore } from '@/features/auth/token'

/** 后端 detail 可能是字符串、带 message 的对象，或 FastAPI 校验错误数组 */
export type ApiErrorDetail = string | Record<string, unknown> | unknown[]

export class ApiError extends Error {
  readonly status: number
  readonly detail: ApiErrorDetail

  constructor(status: number, detail: ApiErrorDetail) {
    super(typeof detail === 'string' ? detail : '请求失败')
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export const API_PREFIX = '/api/v1'

/** FastAPI 校验错误体形状：detail 为带 msg/loc 的数组；此处只透传，展示文案在 lib/errors.ts */
interface ValidationErrorBody {
  detail: Array<{ msg: string; loc: (string | number)[] }>
}

export async function readErrorDetail(response: Response): Promise<ApiErrorDetail> {
  const text = await response.text().catch(() => '')
  if (!text) return response.statusText || '请求失败'

  try {
    const body = JSON.parse(text) as { detail?: ApiErrorDetail } | ValidationErrorBody
    if (body.detail !== undefined && body.detail !== null) return body.detail
  } catch {
    // 非 JSON 响应，原样返回
  }
  return text
}

/**
 * 全站唯一的请求出口。集中在这里是为了让鉴权头、错误语义、
 * 401 清理只有一处定义，后续加 token 刷新时不必翻遍调用点。
 */
export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = tokenStore.get()
  // multipart 的边界串必须由浏览器自己生成，预先写死 Content-Type 后端就解析不出字段
  const multipart = init.body instanceof FormData

  const response = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    headers: {
      ...(multipart ? {} : { 'Content-Type': 'application/json' }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  })

  if (!response.ok) {
    // token 失效就地清理，避免后续请求继续带着废 token 反复触发 401
    if (response.status === 401) {
      tokenStore.clear()
    }
    throw new ApiError(response.status, await readErrorDetail(response))
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

/**
 * 拉取二进制响应。JSON 的 request() 会破坏文件流，导出类接口走这里。
 * 成功返回 Response（调用方自行 .blob()）；失败抛 ApiError，detail 可能是对象。
 */
export async function requestBinary(path: string, init: RequestInit = {}): Promise<Response> {
  const token = tokenStore.get()
  const response = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  })

  if (!response.ok) {
    if (response.status === 401) {
      tokenStore.clear()
    }
    throw new ApiError(response.status, await readErrorDetail(response))
  }

  return response
}
