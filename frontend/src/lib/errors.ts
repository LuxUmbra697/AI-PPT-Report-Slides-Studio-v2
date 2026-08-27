import { ApiError, type ApiErrorDetail } from '@/api/client'

function detailToMessage(detail: ApiErrorDetail): string | null {
  if (typeof detail === 'string') return detail

  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0]
    if (first && typeof first === 'object' && 'msg' in first) {
      const msg = (first as { msg: unknown }).msg
      if (typeof msg === 'string') return msg
    }
  }

  if (detail && typeof detail === 'object' && 'message' in detail) {
    const message = (detail as { message: unknown }).message
    if (typeof message === 'string') return message
  }

  return null
}

/** 常见 FastAPI / pydantic 英文校验文案 → 中文 */
function localizeValidationMessage(message: string): string {
  const ge = message.match(/greater than or equal to (\d+)/i)
  if (ge) return `不能小于 ${ge[1]}`
  const le = message.match(/less than or equal to (\d+)/i)
  if (le) return `不能大于 ${le[1]}`
  if (/field required/i.test(message)) return '必填项缺失'
  return message
}

/** 接口错误直接展示后端给的中文说明，其余一律收敛为通用提示 */
export function errorMessage(error: Error | null | undefined, fallback = '操作失败，请稍后重试。') {
  if (!error) return fallback
  if (!(error instanceof ApiError)) return fallback
  const raw = detailToMessage(error.detail)
  if (!raw) return fallback
  return localizeValidationMessage(raw)
}
