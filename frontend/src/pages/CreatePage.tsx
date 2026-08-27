import { ArrowRight, ClipboardType, FileUp, Loader2, Sparkles, Type, X } from 'lucide-react'
import { type ChangeEvent, type DragEvent, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { Button } from '@/components/ui/Button'
import { PillSelect } from '@/components/ui/PillSelect'
import { type DraftMode, useCreateDraft } from '@/features/projects/api'
import {
  DEFAULT_THEME_ID,
  PAGE_COUNT_OPTIONS,
  TONE_OPTIONS,
} from '@/features/projects/options'
import { ACCEPTED_UPLOAD, type Tone } from '@/features/projects/types'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

const MODES: Array<{ mode: DraftMode; label: string; icon: typeof Type; hint: string }> = [
  { mode: 'topic', label: '从主题生成', icon: Sparkles, hint: '一句话说清要讲什么' },
  { mode: 'text', label: '粘贴文字', icon: ClipboardType, hint: '已有内容，自动提炼成要点' },
  { mode: 'document', label: '上传文档', icon: FileUp, hint: '支持 PDF、Word、Markdown、TXT' },
]

const PLACEHOLDER: Record<DraftMode, string> = {
  topic: '例如：2026 上半年增长复盘，讲清三条增长曲线与下半年打法',
  text: '把已有的文字粘进来，会自动提炼成每页要点',
  document: '',
}

const TITLE_MAX = 60

/** 标题由输入内容推出来，用户不必先给文件起名；生成大纲期间可再改 */
function deriveTitle(mode: DraftMode, content: string, files: File[]): string {
  if (mode === 'document') {
    const first = files[0]?.name ?? ''
    return first.replace(/\.[^.]+$/, '').slice(0, TITLE_MAX) || '未命名 PPT'
  }
  const line = content
    .split('\n')
    .map((item) => item.trim())
    .find((item) => item.length > 0)
  return (line ?? '').slice(0, TITLE_MAX) || '未命名 PPT'
}

export default function CreatePage() {
  const navigate = useNavigate()
  const [mode, setMode] = useState<DraftMode>('topic')
  const [content, setContent] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [audience, setAudience] = useState('')
  const [tone, setTone] = useState<NonNullable<Tone>>('professional')
  const [pageCount, setPageCount] = useState(10)
  const [layoutMode, setLayoutMode] = useState<'fixed' | 'flex'>('flex')
  const [contentDensity, setContentDensity] = useState<'concise' | 'medium' | 'detailed'>(
    'medium',
  )
  const [step, setStep] = useState<string | null>(null)
  const create = useCreateDraft()

  const ready = mode === 'document' ? files.length > 0 : content.trim().length > 0
  const busy = create.isPending

  const submit = () => {
    if (!ready || busy) return
    create.mutate(
      {
        mode,
        content: content.trim(),
        files,
        title: deriveTitle(mode, content, files),
        audience: audience.trim() || null,
        tone,
        pageCount,
        themeId: DEFAULT_THEME_ID,
        layoutMode,
        contentDensity,
        onStep: setStep,
      },
      {
        onSuccess: (project) => navigate(`/projects/${project.id}`),
        onSettled: () => setStep(null),
      },
    )
  }

  return (
    <div className="bg-aurora min-h-[calc(100vh-3.5rem)] px-6 py-14">
      <div className="mx-auto max-w-3xl">
        <h1 className="text-center text-[clamp(1.75rem,4vw,2.5rem)] font-semibold tracking-tight">
          想做一份什么 PPT？
        </h1>
        <p className="mt-3 text-center text-sm text-ink-muted">
          先确认大纲，再生成 16:9 页面，导出为可编辑的 PPTX
        </p>

        <div className="mt-8 grid gap-2.5 sm:grid-cols-3">
          {MODES.map(({ mode: value, label, icon: Icon, hint }) => (
            <button
              key={value}
              type="button"
              disabled={busy}
              onClick={() => setMode(value)}
              className={cn(
                'flex flex-col items-start gap-1 rounded-2xl border px-4 py-3.5 text-left transition-all',
                'disabled:cursor-not-allowed',
                value === mode
                  ? 'border-accent bg-surface shadow-card'
                  : 'border-line bg-surface/70 hover:border-line-strong hover:bg-surface',
              )}
            >
              <span
                className={cn(
                  'flex items-center gap-2 text-sm font-semibold',
                  value === mode ? 'text-accent' : 'text-ink',
                )}
              >
                <Icon className="size-4" />
                {label}
              </span>
              <span className="text-xs leading-relaxed text-ink-muted">{hint}</span>
            </button>
          ))}
        </div>

        <div className="mt-4 rounded-3xl border border-line bg-surface p-4 shadow-card">
          {mode === 'document' ? (
            <FileDrop files={files} disabled={busy} onChange={setFiles} />
          ) : (
            <textarea
              value={content}
              disabled={busy}
              rows={mode === 'text' ? 9 : 3}
              maxLength={mode === 'text' ? 20000 : 500}
              placeholder={PLACEHOLDER[mode]}
              onChange={(event) => setContent(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) submit()
              }}
              className="w-full resize-none bg-transparent px-2 py-1.5 text-[15px] leading-relaxed text-ink placeholder:text-ink-muted/70 focus:outline-none"
            />
          )}

          <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-line/80 pt-3">
            <PillSelect
              label="页数"
              disabled={busy}
              value={pageCount}
              options={PAGE_COUNT_OPTIONS}
              onChange={(next) => setPageCount(Number(next))}
            />
            <PillSelect
              label="排版"
              disabled={busy}
              value={layoutMode}
              options={[
                { value: 'flex', label: '灵活排版', description: '块数量与排布随内容变化' },
                { value: 'fixed', label: '固定版式', description: '槽位稳定，适合可控版面' },
              ]}
              onChange={(next) => setLayoutMode(next as 'fixed' | 'flex')}
            />
            <PillSelect
              label="文字量"
              disabled={busy}
              value={contentDensity}
              options={[
                { value: 'concise', label: '简洁', description: '少而精，一页抓一个重点' },
                { value: 'medium', label: '中等', description: '结论 + 适量支撑细节' },
                { value: 'detailed', label: '详细', description: '信息更满，可含表图' },
              ]}
              onChange={(next) =>
                setContentDensity(next as 'concise' | 'medium' | 'detailed')
              }
            />
            <PillSelect
              label="语气"
              disabled={busy}
              value={tone}
              options={TONE_OPTIONS}
              onChange={(next) => setTone(next as NonNullable<Tone>)}
            />
            <input
              value={audience}
              disabled={busy}
              maxLength={80}
              placeholder="受众（可选）"
              aria-label="受众"
              onChange={(event) => setAudience(event.target.value)}
              className="h-9 w-40 rounded-full bg-surface-soft/90 px-3.5 text-[13px] text-ink-soft ring-1 ring-transparent transition-all placeholder:text-ink-muted hover:bg-white hover:ring-line hover:shadow-sm focus:bg-white focus:ring-line focus:outline-none disabled:opacity-45"
            />
            <span className="inline-flex h-9 items-center rounded-full bg-surface-soft/90 px-3 text-[13px] font-medium text-ink-muted">
              16:9
            </span>

            <Button
              size="md"
              disabled={!ready || busy}
              onClick={submit}
              className="ml-auto"
            >
              {busy ? <Loader2 className="size-4 animate-spin" /> : null}
              {busy ? '生成中…' : '生成大纲'}
              {!busy && <ArrowRight className="size-4" />}
            </Button>
          </div>
        </div>

        <div className="mt-4 min-h-6 text-center">
          {busy && step && (
            <p aria-live="polite" className="text-[13px] text-ink-muted">
              {step}
            </p>
          )}
          {create.isError && (
            <p role="alert" className="text-[13px] text-negative">
              {errorMessage(create.error, '创建失败，请检查输入后重试')}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

function FileDrop({
  files,
  disabled,
  onChange,
}: {
  files: File[]
  disabled?: boolean
  onChange: (files: File[]) => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  const append = (incoming: FileList | null) => {
    if (!incoming?.length) return
    const next = [...files]
    for (const file of Array.from(incoming)) {
      if (!next.some((item) => item.name === file.name && item.size === file.size)) {
        next.push(file)
      }
    }
    onChange(next)
  }

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragging(false)
    if (!disabled) append(event.dataTransfer.files)
  }

  const onPick = (event: ChangeEvent<HTMLInputElement>) => {
    append(event.target.files)
    event.target.value = ''
  }

  return (
    <div className="flex flex-col gap-3">
      <div
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          'rounded-2xl border border-dashed px-6 py-10 text-center transition-colors',
          dragging ? 'border-accent bg-accent-soft' : 'border-line-strong bg-surface-soft',
        )}
      >
        <FileUp className="mx-auto mb-3 size-5 text-ink-muted" />
        <p className="text-sm text-ink-soft">
          拖到这里，或
          <button
            type="button"
            disabled={disabled}
            onClick={() => inputRef.current?.click()}
            className="mx-1 font-medium text-accent underline-offset-2 hover:underline disabled:opacity-50"
          >
            选择文件
          </button>
          （可多选）
        </p>
        <p className="mt-1.5 text-xs text-ink-muted">支持 PDF、Word、Markdown、TXT</p>
        <input
          ref={inputRef}
          type="file"
          multiple
          hidden
          accept={ACCEPTED_UPLOAD}
          onChange={onPick}
        />
      </div>

      {files.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {files.map((file) => (
            <li
              key={`${file.name}-${file.size}`}
              className="flex items-center gap-2 rounded-full bg-surface-soft py-1.5 pr-2 pl-3.5 text-[13px] text-ink-soft"
            >
              <span className="max-w-56 truncate">{file.name}</span>
              <button
                type="button"
                disabled={disabled}
                aria-label={`移除 ${file.name}`}
                onClick={() => onChange(files.filter((item) => item !== file))}
                className="grid size-5 place-items-center rounded-full text-ink-muted transition-colors hover:bg-line hover:text-ink disabled:opacity-50"
              >
                <X className="size-3" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
