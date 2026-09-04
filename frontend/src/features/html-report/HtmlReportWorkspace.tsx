import { Code2, Download, Loader2, RefreshCw } from 'lucide-react'
import { WorkbenchHeader } from '@/components/WorkbenchHeader'
import { Button } from '@/components/ui/Button'
import { type DeckExportFormat, useExportDeck } from '@/features/deck/api'
import {
  useGenerateHtmlReport,
  useHtmlReport,
  useHtmlReportPreview,
} from '@/features/html-report/api'
import type { ProjectDetail } from '@/features/projects/types'
import { errorMessage } from '@/lib/errors'

const HTML_EXPORT: { format: DeckExportFormat; label: string; icon: typeof Download } = {
  format: 'html',
  label: '下载 HTML',
  icon: Download,
}

/** HTML 项目的独立终点：显示真实报告，而不是复用幻灯片编辑器。 */
export function HtmlReportWorkspace({ project }: { project: ProjectDetail }) {
  const report = useHtmlReport(project.id)
  const generate = useGenerateHtmlReport(project.id)
  const legacyReady = report.data?.status === 'ready' && !report.data.has_document
  const ready = report.data?.status === 'ready' && report.data.has_document
  const preview = useHtmlReportPreview(project.id, report.data?.job_id, ready)
  const exporter = useExportDeck(project.id)

  const start = (regenerate = false) => generate.mutate(regenerate)
  const message =
    report.data?.status === 'generating'
      ? 'AI 正在从零设计并编写完整的 HTML、CSS 与 JavaScript…'
      : report.data?.status === 'failed'
        ? report.data.error ?? 'HTML 报告生成失败。'
        : legacyReady
          ? '这份报告由旧版样式引擎生成。重新生成后将由 AI 直接创作完整网页。'
        : '大纲已确认，准备生成 HTML 报告。'

  return (
    <div className="flex min-h-screen flex-col bg-aurora">
      <WorkbenchHeader
        title={project.title}
        meta={<span className="rounded-full bg-accent-soft px-2 py-0.5 text-[11px] font-medium text-accent">HTML 报告</span>}
      >
        {ready && (
          <>
            <Button
              variant="ghost"
              size="sm"
              disabled={generate.isPending}
              onClick={() => start(true)}
            >
              <RefreshCw className="size-3.5" />
              重新生成
            </Button>
            <Button
              variant="ghost"
              size="sm"
              disabled={exporter.isPending}
              onClick={() => exporter.mutate({ format: HTML_EXPORT.format, title: project.title })}
            >
              <HTML_EXPORT.icon className="size-3.5" />
              {HTML_EXPORT.label}
            </Button>
          </>
        )}
      </WorkbenchHeader>

      {!ready ? (
        <div className="mx-auto grid w-full max-w-xl flex-1 place-items-center px-6 py-16">
          <div className="w-full rounded-3xl border border-line bg-surface px-8 py-10 text-center shadow-card">
            {report.data?.status === 'generating' || generate.isPending ? (
              <Loader2 className="mx-auto size-6 animate-spin text-accent" />
            ) : (
              <Code2 className="mx-auto size-6 text-accent" />
            )}
            <h2 className="mt-4 text-lg font-semibold">生成 HTML 报告</h2>
            <p className="mt-2 text-sm leading-relaxed text-ink-muted">{message}</p>
            {report.data?.status !== 'generating' && !generate.isPending && (
              <Button
                className="mt-6"
                onClick={() => start(report.data?.status === 'failed' || legacyReady)}
              >
                <RefreshCw className="size-4" />
                {report.data?.status === 'failed' || legacyReady ? '重新生成 HTML' : '开始生成 HTML'}
              </Button>
            )}
            {(report.isError || generate.isError) && (
              <p role="alert" className="mt-4 text-xs text-negative">
                {errorMessage(report.error ?? generate.error, '无法启动 HTML 报告生成')}
              </p>
            )}
          </div>
        </div>
      ) : preview.isPending ? (
        <div className="grid flex-1 place-items-center">
          <Loader2 className="size-5 animate-spin text-ink-muted" />
        </div>
      ) : preview.isError ? (
        <div className="grid flex-1 place-items-center px-6">
          <div className="rounded-3xl border border-line bg-surface px-8 py-10 text-center shadow-card">
            <p className="text-sm text-negative">{errorMessage(preview.error, 'HTML 预览加载失败')}</p>
            <Button variant="ghost" className="mt-5" onClick={() => void preview.refetch()}>
              重试加载
            </Button>
          </div>
        </div>
      ) : (
        <div className="min-h-0 flex-1 p-3 sm:p-5">
          <iframe
            title={`${project.title} HTML 报告`}
            srcDoc={preview.data}
            sandbox="allow-scripts"
            referrerPolicy="no-referrer"
            className="h-[calc(100vh-5.75rem)] w-full rounded-2xl border border-line bg-white shadow-card"
          />
        </div>
      )}
    </div>
  )
}
