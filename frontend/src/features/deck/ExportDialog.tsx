import { AlertTriangle, CheckCircle2, Download, Loader2, RotateCcw, XCircle } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { useDeckQuality, useExportDeck } from '@/features/deck/api'
import { classifyExportError, type ExportFailure } from '@/features/deck/exportErrors'
import type { Deck, DeckSlide, ExportCheckReport, StructureIssue } from '@/features/deck/types'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

/** 导出前的检查结论。拿不到报告与「报告说有错」是两回事，必须分开表达。 */
type CheckState =
  | { kind: 'unavailable'; message: string }
  | { kind: 'incomplete' }
  | { kind: 'blocked'; errorCount: number }
  | { kind: 'ready'; warningCount: number }

function resolveCheckState({
  report,
  error,
  incomplete,
  errorCount,
  warningCount,
}: {
  report: ExportCheckReport | undefined
  error: Error | null
  incomplete: boolean
  errorCount: number
  warningCount: number
}): CheckState {
  if (incomplete) return { kind: 'incomplete' }
  if (!report) {
    return {
      kind: 'unavailable',
      message: errorMessage(error, '检查没能完成，可能是服务未启动或网络中断。'),
    }
  }
  if (!report.export_allowed || errorCount > 0) return { kind: 'blocked', errorCount }
  return { kind: 'ready', warningCount }
}

/**
 * 导出面板：先给结论，再给可点击定位的问题清单。
 * 错误必须修复，告警不阻断——两者在视觉上必须能一眼分开。
 */
export function ExportDialog({
  projectId,
  deck,
  onClose,
  onLocate,
}: {
  projectId: string
  deck: Deck
  onClose: () => void
  onLocate: (slideId: string) => void
}) {
  const settled = deck.status === 'ready' || deck.status === 'partial'
  const quality = useDeckQuality(projectId, settled)
  const exporter = useExportDeck(projectId, `${deck.title}.pptx`)
  const [done, setDone] = useState(false)

  const report = quality.data
  const issues = report?.issues ?? []
  const errors = issues.filter((issue) => issue.severity === 'error')
  const warnings = issues.filter((issue) => issue.severity === 'warning')
  const incomplete = deck.slides.some((slide) => slide.status !== 'ready')
  const state = resolveCheckState({
    report,
    error: quality.error,
    incomplete,
    errorCount: errors.length,
    warningCount: warnings.length,
  })
  const allowed = state.kind === 'ready'
  const failure = exporter.isError ? classifyExportError(exporter.error) : null

  const locate = (slideId: string) => {
    onLocate(slideId)
    onClose()
  }

  return (
    <Dialog
      title="导出 PPTX"
      description="导出前会检查结构与文字溢出，通过后生成原生可编辑的文件"
      onClose={onClose}
      footer={
        <>
          {done && !exporter.isPending && (
            <span className="mr-auto flex items-center gap-1.5 text-[13px] text-positive">
              <CheckCircle2 className="size-4" />
              已开始下载
            </span>
          )}
          <Button variant="ghost" onClick={onClose}>
            关闭
          </Button>
          <Button
            disabled={!allowed || exporter.isPending}
            onClick={() => {
              setDone(false)
              exporter.mutate(undefined, { onSuccess: () => setDone(true) })
            }}
          >
            {exporter.isPending ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Download className="size-4" />
            )}
            {exporter.isPending ? '正在导出…' : done ? '再导出一次' : '导出 PPTX'}
          </Button>
        </>
      }
    >
      {quality.isPending && quality.isFetching ? (
        <p className="py-6 text-center text-sm text-ink-muted" aria-live="polite">
          正在检查…
        </p>
      ) : (
        <div className="flex flex-col gap-4">
          <Verdict
            state={state}
            retrying={quality.isFetching}
            onRetry={() => void quality.refetch()}
          />

          {report && !report.fonts_precise && (
            <p className="rounded-xl bg-warning/8 px-4 py-3 text-[13px] leading-relaxed text-warning">
              度量字体未就绪，文字溢出为估算值，并非精确结论。
            </p>
          )}

          {failure && <FailureNote failure={failure} />}

          {errors.length > 0 && (
            <IssueList
              tone="error"
              label="必须修复"
              issues={errors}
              slides={deck.slides}
              onLocate={locate}
            />
          )}

          {warnings.length > 0 && (
            <IssueList
              tone="warning"
              label="建议关注，不阻断导出"
              issues={warnings}
              slides={deck.slides}
              onLocate={locate}
            />
          )}
        </div>
      )}
    </Dialog>
  )
}

function verdictText(state: CheckState): { title: string; summary: string } {
  switch (state.kind) {
    case 'unavailable':
      return { title: '检查没有完成', summary: `${state.message}重试检查后才能判断能否导出。` }
    case 'incomplete':
      return { title: '暂时不能导出', summary: '仍有页面没有生成成功，先重试失败页再导出。' }
    case 'blocked':
      return {
        title: '暂时不能导出',
        summary:
          state.errorCount > 0
            ? `有 ${state.errorCount} 处必须修复，修好后即可导出。`
            : '检查未通过但没有给出具体问题，请重试检查。',
      }
    case 'ready':
      return {
        title: '可以导出',
        summary:
          state.warningCount > 0
            ? `可以导出，有 ${state.warningCount} 处建议关注。`
            : '检查通过，可以导出。',
      }
  }
}

function Verdict({
  state,
  retrying,
  onRetry,
}: {
  state: CheckState
  retrying: boolean
  onRetry: () => void
}) {
  const allowed = state.kind === 'ready'
  const Icon = allowed ? CheckCircle2 : state.kind === 'unavailable' ? AlertTriangle : XCircle
  const tone = allowed ? 'text-positive' : state.kind === 'unavailable' ? 'text-warning' : 'text-negative'
  const { title, summary } = verdictText(state)
  const retryable = state.kind === 'unavailable' || (state.kind === 'blocked' && state.errorCount === 0)

  return (
    <div
      className={cn(
        'flex items-start gap-3 rounded-2xl px-4 py-3.5',
        allowed ? 'bg-positive/8' : state.kind === 'unavailable' ? 'bg-warning/8' : 'bg-negative/8',
      )}
    >
      <Icon className={cn('mt-0.5 size-4.5 shrink-0', tone)} />
      <div className="min-w-0 flex-1">
        <p className={cn('text-sm font-semibold', tone)}>{title}</p>
        <p className="mt-0.5 text-[13px] text-ink-soft">{summary}</p>
        {retryable && (
          <Button
            variant="ghost"
            size="sm"
            className="mt-2.5"
            disabled={retrying}
            onClick={onRetry}
          >
            {retrying ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <RotateCcw className="size-3.5" />
            )}
            重新检查
          </Button>
        )}
      </div>
    </div>
  )
}

function IssueList({
  tone,
  label,
  issues,
  slides,
  onLocate,
}: {
  tone: 'error' | 'warning'
  label: string
  issues: StructureIssue[]
  slides: DeckSlide[]
  onLocate: (slideId: string) => void
}) {
  return (
    <section>
      <p
        className={cn(
          'mb-2 flex items-center gap-1.5 text-xs font-semibold',
          tone === 'error' ? 'text-negative' : 'text-warning',
        )}
      >
        {tone === 'error' ? <XCircle className="size-3.5" /> : <AlertTriangle className="size-3.5" />}
        {label}
      </p>
      <ul className="flex flex-col gap-1.5">
        {issues.map((issue, index) => {
          const slide = slides.find((item) => item.id === issue.slide_id)
          return (
            <li key={`${issue.slide_id}-${issue.slot_id ?? 'page'}-${index}`}>
              <button
                type="button"
                onClick={() => onLocate(issue.slide_id)}
                className="flex w-full items-start gap-3 rounded-xl border border-line px-3.5 py-2.5 text-left transition-colors hover:border-line-strong hover:bg-surface-soft"
              >
                <span className="mt-0.5 shrink-0 rounded-md bg-surface-soft px-1.5 py-0.5 text-[11px] font-medium text-ink-muted tabular-nums">
                  {slide ? `第 ${slide.position} 页` : '整份'}
                </span>
                <span className="min-w-0 flex-1 text-[13px] leading-relaxed text-ink-soft">
                  {issue.message}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function FailureNote({ failure }: { failure: ExportFailure }) {
  const hint =
    failure.kind === 'verify'
      ? '文件没有生成，可编辑性检查未通过，可直接重试。'
      : failure.kind === 'server'
        ? '服务端出错，可直接重试。'
        : failure.kind === 'incomplete'
          ? '先把未完成的页面补齐。'
          : null

  return (
    <div role="alert" className="rounded-xl bg-negative/8 px-4 py-3">
      <p className="text-[13px] font-medium text-negative">{failure.message}</p>
      {hint && <p className="mt-1 text-xs text-ink-soft">{hint}</p>}
      {failure.kind === 'verify' && failure.issues.length > 0 && (
        <ul className="mt-2 flex flex-col gap-1">
          {failure.issues.map((issue, index) => (
            <li key={`${issue.check}-${index}`} className="text-xs text-negative">
              {issue.slide_index != null ? `第 ${issue.slide_index} 页 · ` : ''}
              {issue.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
