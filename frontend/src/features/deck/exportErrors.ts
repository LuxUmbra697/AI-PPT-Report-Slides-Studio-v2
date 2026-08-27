import { ApiError } from '@/api/client'
import type { ExportCheckReport, ExportVerifyIssue } from '@/features/deck/types'
import { errorMessage } from '@/lib/errors'

export type ExportFailure =
  | { kind: 'check'; message: string; report: ExportCheckReport }
  | { kind: 'incomplete'; message: string }
  | { kind: 'verify'; message: string; issues: ExportVerifyIssue[] }
  | { kind: 'server'; message: string }
  | { kind: 'unknown'; message: string }

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function asVerifyIssues(value: unknown): ExportVerifyIssue[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((item) => {
    const row = asRecord(item)
    if (!row || typeof row.message !== 'string' || typeof row.check !== 'string') return []
    return [
      {
        check: row.check,
        message: row.message,
        slide_index: typeof row.slide_index === 'number' ? row.slide_index : null,
        shape: typeof row.shape === 'string' ? row.shape : null,
      },
    ]
  })
}

function asReport(value: unknown): ExportCheckReport | null {
  const row = asRecord(value)
  if (!row || typeof row.export_allowed !== 'boolean') return null
  const issues = Array.isArray(row.issues) ? row.issues : []
  return {
    export_allowed: row.export_allowed,
    fonts_precise: row.fonts_precise !== false,
    issues: issues as ExportCheckReport['issues'],
  }
}

export function classifyExportError(error: unknown): ExportFailure {
  if (!(error instanceof ApiError)) {
    return { kind: 'unknown', message: errorMessage(error instanceof Error ? error : null) }
  }

  const detail = error.detail
  const record = asRecord(detail)

  if (error.status === 409) {
    if (record?.report) {
      const report = asReport(record.report)
      if (report) {
        return {
          kind: 'check',
          message:
            typeof record.message === 'string'
              ? record.message
              : '导出前检查未通过，存在必须修复的问题',
          report,
        }
      }
    }
    return {
      kind: 'incomplete',
      message:
        typeof detail === 'string'
          ? detail
          : '页面尚未全部生成完成，无法导出',
    }
  }

  if (error.status === 422 && record?.issues) {
    return {
      kind: 'verify',
      message:
        typeof record.message === 'string'
          ? record.message
          : '导出回读验证未通过，未返回文件',
      issues: asVerifyIssues(record.issues),
    }
  }

  if (error.status >= 500) {
    return {
      kind: 'server',
      message: errorMessage(error, '导出过程出错，请稍后重试'),
    }
  }

  return { kind: 'unknown', message: errorMessage(error) }
}
