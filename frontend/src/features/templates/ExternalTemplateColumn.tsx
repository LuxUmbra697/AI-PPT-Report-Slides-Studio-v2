import { FileStack, Image, Layers3, LayoutTemplate, RefreshCw, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import {
  type ExternalTemplate,
  useExternalTemplates,
  useRefreshExternalTemplates,
} from '@/features/templates/api'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

function statusLabel(template: ExternalTemplate): string {
  switch (template.analysis_status) {
    case 'ready':
      return 'AI 已解析'
    case 'partial':
      return '部分 AI 解析'
    case 'unavailable':
      return '等待配置 AI'
    case 'failed':
      return '结构读取受限'
    default:
      return '可按需 AI 解析'
  }
}

function templateCover(template: ExternalTemplate) {
  const [background = '#202330', accent = '#F36B99', detail = '#FFFFFF'] = template.palette
  return {
    background: `linear-gradient(135deg, ${background} 0%, ${accent} 150%)`,
    color: detail,
  }
}

/** 独立于内置主题的 Template/ 文件夹选择列。 */
export function ExternalTemplateColumn({
  selectedId,
  disabled,
  onSelect,
}: {
  selectedId: string | null | undefined
  disabled?: boolean
  onSelect: (template: ExternalTemplate) => void
}) {
  const templates = useExternalTemplates()
  const refresh = useRefreshExternalTemplates()

  return (
    <section className="flex flex-col gap-2.5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-ink-soft">外部 PPT 模板</p>
          <p className="mt-0.5 text-[11px] leading-relaxed text-ink-muted">
            单独读取 <code>Template/</code>；逐页逆向母版、版式与页面对象后，应用可编辑风格。
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          disabled={disabled || refresh.isPending}
          onClick={() => refresh.mutate()}
          title="调用 DeepSeek 和百炼 Qwen-VL，补全图片语义与逐页版式归纳"
          className="shrink-0"
        >
          <RefreshCw className={cn('size-3.5', refresh.isPending && 'animate-spin')} />
          {refresh.isPending ? '解析中' : '重新解析'}
        </Button>
      </div>

      {templates.isPending && (
        <div className="rounded-xl border border-dashed border-line px-3 py-4 text-center text-xs text-ink-muted">
          正在读取 Template 文件夹…
        </div>
      )}

      {templates.data?.length === 0 && (
        <div className="rounded-xl border border-dashed border-line px-3 py-4 text-xs leading-relaxed text-ink-muted">
          将 <code>.pptx</code> 放入项目根目录的 <code>Template/</code>，然后点击“重新解析”。
        </div>
      )}

      <div className="flex flex-col gap-2">
        {templates.data?.map((template) => {
          const selected = selectedId === template.id
          return (
            <button
              key={template.id}
              type="button"
              disabled={disabled}
              aria-pressed={selected}
              onClick={() => onSelect(template)}
              className={cn(
                'overflow-hidden rounded-xl border text-left transition-colors',
                selected ? 'border-accent ring-1 ring-accent/30' : 'border-line hover:border-line-strong',
                'disabled:opacity-50',
              )}
            >
              <div style={templateCover(template)} className="relative min-h-20 overflow-hidden px-3 py-2.5">
                <span className="absolute right-2 top-2 opacity-25">
                  <LayoutTemplate className="size-10" />
                </span>
                <p className="relative max-w-[80%] text-sm font-semibold leading-tight">{template.name}</p>
                <p className="relative mt-1 text-[10px] opacity-80">
                  {template.slide_count} 页 · {template.layout_count} 布局 · {template.aspect_ratio}
                </p>
              </div>
              <div className="flex flex-col gap-1.5 px-3 py-2.5">
                <span className="flex items-center gap-1.5 text-[11px] text-ink-muted">
                  <FileStack className="size-3 shrink-0" />
                  {statusLabel(template)}
                </span>
                <span className="flex items-center gap-1.5 text-[11px] leading-relaxed text-ink-muted">
                  <Layers3 className="size-3 shrink-0" />
                  {template.element_count} 个对象 · {template.background_count} 页背景 ·{' '}
                  {template.component_count} 类组件
                </span>
                {template.structural_summary && (
                  <p className="text-[11px] leading-relaxed text-ink-soft">
                    {template.structural_summary}
                  </p>
                )}
                {template.style_summary && (
                  <p className="text-[11px] leading-relaxed text-ink-soft">{template.style_summary}</p>
                )}
                {template.image_summary && (
                  <p className="flex gap-1 text-[11px] leading-relaxed text-ink-muted">
                    <Image className="mt-0.5 size-3 shrink-0" />
                    {template.image_summary}
                  </p>
                )}
              </div>
            </button>
          )
        })}
      </div>

      <p className="flex gap-1.5 text-[11px] leading-relaxed text-ink-muted">
        <Sparkles className="mt-0.5 size-3 shrink-0 text-accent" />
        AI 解析只在点“重新解析”时调用：先从 PPTX 读取母版、版式、页面坐标与层级，
        再由 DeepSeek 概括构图/文案，Qwen-VL 识别图片资产。
      </p>

      {(templates.isError || refresh.isError) && (
        <p role="alert" className="rounded-xl bg-negative/8 px-3 py-2 text-xs text-negative">
          {errorMessage(templates.error ?? refresh.error)}
        </p>
      )}
    </section>
  )
}
