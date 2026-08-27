import { Check, GripVertical, Loader2, Plus, RefreshCw, Sparkles, Trash2, X } from 'lucide-react'
import { type ReactNode, useEffect, useMemo, useRef, useState } from 'react'
import { WorkbenchHeader } from '@/components/WorkbenchHeader'
import { Button } from '@/components/ui/Button'
import { useGenerateOutline, useOutline, useUpdateOutline } from '@/features/outline/api'
import type { Outline, OutlinePage } from '@/features/outline/types'
import { useConfirmAndGenerate } from '@/features/outline/useConfirmAndGenerate'
import { useOutlineProgress } from '@/features/outline/useOutlineProgress'
import { useUpdateProject } from '@/features/projects/api'
import { PAGE_COUNT_RANGE, type ProjectDetail } from '@/features/projects/types'
import { moveItem, useDragSort } from '@/hooks/useDragSort'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'
import { themeList } from '@/render/design'
import { ThemeCover } from '@/render/ThemeCover'

const MAX_KEY_POINTS = 5
const MIN_KEY_POINTS = 2

export function OutlineWorkspace({ project }: { project: ProjectDetail }) {
  const outlineQuery = useOutline(project.id)
  const generate = useGenerateOutline(project.id)
  const outline = outlineQuery.data ?? null
  const progress = useOutlineProgress(project.id, outline?.status === 'generating')

  if (outlineQuery.isPending) {
    return (
      <Shell title={project.title}>
        <CenterCard>
          <Loader2 className="mx-auto size-5 animate-spin text-ink-muted" />
          <p className="mt-4 text-sm text-ink-muted">正在读取大纲…</p>
        </CenterCard>
      </Shell>
    )
  }

  if (outline?.status === 'generating') {
    return (
      <Shell title={project.title}>
        <CenterCard>
          <p className="text-sm font-medium">{progress.event?.message ?? '正在规划每一页…'}</p>
          <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-line">
            <div
              className="h-full rounded-full bg-accent transition-[width] duration-500"
              style={{ width: `${progress.event?.progress ?? 8}%` }}
            />
          </div>
          <p className="mt-3 text-xs text-ink-muted">
            {progress.connectionError ? '进度连接中断，正在重连…' : '大纲只规划目标与要点，不生成正文'}
          </p>
        </CenterCard>
      </Shell>
    )
  }

  if (outline == null || outline.status === 'failed') {
    return (
      <Shell title={project.title}>
        <CenterCard>
          <p className="text-sm text-ink-soft">
            {outline?.error ?? (outline ? '大纲生成失败。' : '还没有大纲。')}
          </p>
          <Button
            className="mt-5"
            disabled={generate.isPending}
            onClick={() => generate.mutate()}
          >
            <RefreshCw className={cn('size-4', generate.isPending && 'animate-spin')} />
            {generate.isPending ? '正在提交…' : '重新生成大纲'}
          </Button>
          {generate.isError && (
            <p role="alert" className="mt-3 text-xs text-negative">
              {errorMessage(generate.error)}
            </p>
          )}
        </CenterCard>
      </Shell>
    )
  }

  return <OutlineEditor project={project} outline={outline} />
}

function OutlineEditor({ project, outline }: { project: ProjectDetail; outline: Outline }) {
  const [pages, setPages] = useState<OutlinePage[]>(outline.pages)
  const [themeId, setThemeId] = useState(project.theme_id)
  const target = project.page_count

  const save = useUpdateOutline(project.id)
  const updateProject = useUpdateProject(project.id)
  const regenerate = useGenerateOutline(project.id)
  const launch = useConfirmAndGenerate(project.id)

  useEffect(() => setPages(outline.pages), [outline.pages, outline.revision])

  const dirty = useMemo(
    () => JSON.stringify(pages) !== JSON.stringify(outline.pages),
    [outline.pages, pages],
  )
  const countValid = pages.length === target
  const incomplete = pages.some(pageIncomplete)
  // 刚点「+ 要点」的空行：暂停 autosave，避免 normalize 后空行被立刻清掉
  const draftingPoint = pages.some((page) => page.key_points.some((point) => point.trim().length === 0))
  const persisting = save.isPending || updateProject.isPending
  const autosave = useAutosave({
    revision: outline.revision,
    pages,
    pageCount: target,
    dirty,
    draftingPoint,
    // 页数不一致时仍保存：先对齐 page_count，避免增删页后改动卡在「待保存」
    enabled: dirty && !incomplete && !draftingPoint && !launch.isPending,
    saving: persisting,
    save: async ({ revision, pages: nextPages }) => {
      try {
        if (nextPages.length !== target) {
          await updateProject.mutateAsync({ page_count: nextPages.length })
        }
        await save.mutateAsync({ revision, pages: nextPages })
        save.reset()
        updateProject.reset()
        launch.reset()
      } catch {
        // 失败信息由 actionError 统一展示
      }
    },
  })

  const drag = useDragSort((from, to) => setPages((current) => moveItem(current, from, to)))

  const changePage = (index: number, next: OutlinePage) =>
    setPages((current) => current.map((page, i) => (i === index ? next : page)))

  const startGeneration = async () => {
    if (incomplete || draftingPoint || launch.isPending) return
    // 页数被用户改过时先对齐目标，再走确认+生成
    if (!countValid) {
      await updateProject.mutateAsync({ page_count: pages.length })
    }
    // 确认成功后大纲状态变为 confirmed，页面自身会切到编辑工作台，无需跳转
    launch.mutate({
      revision: outline.revision,
      ...(dirty ? { pages: normalizePages(pages) } : {}),
      ...(themeId === project.theme_id ? {} : { themeId }),
    })
  }

  const actionError = launch.error ?? save.error ?? updateProject.error ?? regenerate.error

  return (
    <Shell
      title={project.title}
      meta={
        <span
          className={cn(
            'shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium tabular-nums',
            countValid ? 'bg-surface-soft text-ink-muted' : 'bg-warning/12 text-warning',
          )}
        >
          {pages.length} / {target} 页
        </span>
      }
      actions={
        <>
          <span className="mr-1 text-xs text-ink-muted">{autosave}</span>
          <Button
            variant="ghost"
            size="sm"
            disabled={regenerate.isPending || launch.isPending}
            onClick={() => {
              launch.reset()
              save.reset()
              updateProject.reset()
              regenerate.mutate()
            }}
          >
            <RefreshCw className={cn('size-3.5', regenerate.isPending && 'animate-spin')} />
            重新生成
          </Button>
          <Button
            size="sm"
            disabled={incomplete || draftingPoint || launch.isPending || updateProject.isPending}
            onClick={() => void startGeneration()}
          >
            {launch.isPending ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
            {launch.isPending ? '启动中…' : '生成 PPT'}
          </Button>
        </>
      }
    >
      <div className="mx-auto grid max-w-6xl gap-8 px-6 py-8 lg:grid-cols-[minmax(0,1fr)_19rem]">
        <div>
          <div className="mb-5">
            <h2 className="text-xl font-semibold tracking-tight">确认大纲</h2>
            <p className="mt-1.5 text-sm text-ink-muted">
              改标题、改要点、增删页、拖拽排序，改完自动保存。确认后开始生成 16:9 页面。
            </p>
          </div>

          {actionError && (
            <p role="alert" className="mb-4 rounded-xl bg-negative/8 px-4 py-3 text-sm text-negative">
              {errorMessage(actionError)}
            </p>
          )}

          <ol className="flex flex-col gap-3">
            {pages.map((page, index) => (
              <PageCard
                key={page.id}
                page={page}
                index={index}
                dragProps={drag.itemProps(index)}
                dragOver={drag.overIndex === index}
                dragging={drag.draggingIndex === index}
                canRemove={pages.length > PAGE_COUNT_RANGE.min}
                onChange={(next) => changePage(index, next)}
                onRemove={() => setPages((current) => current.filter((_, i) => i !== index))}
              />
            ))}
          </ol>

          {pages.length < PAGE_COUNT_RANGE.max && (
            <button
              type="button"
              onClick={() => setPages((current) => [...current, blankPage(current.length + 1)])}
              className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-2xl border border-dashed border-line-strong py-3.5 text-[13px] text-ink-muted transition-colors hover:border-accent hover:text-accent"
            >
              <Plus className="size-4" />
              添加一页
            </button>
          )}

          {!countValid && (
            <p className="mt-3 text-center text-xs text-ink-muted">
              页数已改为 {pages.length}，保存时会同步目标页数。
            </p>
          )}
          {pages.length === PAGE_COUNT_RANGE.min && (
            <p className="mt-3 text-center text-xs text-ink-muted">最少 {PAGE_COUNT_RANGE.min} 页。</p>
          )}
          {incomplete && (
            <p className="mt-3 text-center text-xs text-warning">
              每页都需要标题、目标和至少两条要点。
            </p>
          )}
          {draftingPoint && (
            <p className="mt-3 text-center text-xs text-ink-muted">填写或删除空要点后自动保存。</p>
          )}
        </div>

        <aside className="flex flex-col gap-3 lg:sticky lg:top-20 lg:self-start">
          <div>
            <h3 className="text-sm font-semibold tracking-tight">外观</h3>
            <p className="mt-1 text-xs text-ink-muted">决定成品的字体、配色与气质；切换后点「生成 PPT」时生效</p>
          </div>
          {themeList.map((theme) => (
            <button
              key={theme.id}
              type="button"
              aria-pressed={theme.id === themeId}
              onClick={() => setThemeId(theme.id)}
              className={cn(
                'group overflow-hidden rounded-2xl border bg-surface text-left transition-all',
                theme.id === themeId
                  ? 'border-accent shadow-card ring-1 ring-accent'
                  : 'border-line hover:border-line-strong hover:shadow-card',
              )}
            >
              <ThemeCover theme={theme} title={project.title} />
              <div className="flex items-center gap-2 px-3 py-2.5">
                <span className="flex-1 truncate text-[13px] font-medium">{theme.name}</span>
                {theme.id === themeId && <Check className="size-3.5 shrink-0 text-accent" />}
              </div>
            </button>
          ))}
          <p className="mt-1 text-xs leading-relaxed text-ink-muted">
            配图会自动匹配；素材不可用时会退化为纯文字版式，不会留下空位。
          </p>
        </aside>
      </div>
    </Shell>
  )
}

function PageCard({
  page,
  index,
  dragProps,
  dragOver,
  dragging,
  canRemove,
  onChange,
  onRemove,
}: {
  page: OutlinePage
  index: number
  dragProps: Record<string, unknown>
  dragOver: boolean
  dragging: boolean
  canRemove: boolean
  onChange: (page: OutlinePage) => void
  onRemove: () => void
}) {
  const keyPoints = page.key_points

  const changePoint = (pointIndex: number, value: string) => {
    const next = [...keyPoints]
    next[pointIndex] = value
    onChange({ ...page, key_points: next })
  }

  return (
    <li
      {...dragProps}
      className={cn(
        'group relative rounded-2xl border bg-surface px-4 py-4 transition-all',
        dragOver ? 'border-accent' : 'border-line hover:shadow-card',
        dragging && 'opacity-50',
      )}
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex items-center gap-1 text-ink-muted">
          <GripVertical className="size-4 cursor-grab opacity-0 transition-opacity group-hover:opacity-100" />
          <span className="w-5 text-[13px] font-semibold tabular-nums">{index + 1}</span>
        </span>

        <div className="min-w-0 flex-1">
          <input
            aria-label={`第 ${index + 1} 页标题`}
            value={page.title}
            maxLength={100}
            onChange={(event) => onChange({ ...page, title: event.target.value })}
            className="w-full rounded-lg bg-transparent px-1.5 py-1 text-[15px] font-semibold tracking-tight transition-colors hover:bg-surface-soft focus:bg-surface-soft focus:outline-none"
          />
          <textarea
            aria-label={`第 ${index + 1} 页目标`}
            value={page.objective}
            rows={2}
            maxLength={300}
            placeholder="这一页要让人明白什么"
            onChange={(event) => onChange({ ...page, objective: event.target.value })}
            className="mt-1 w-full resize-none rounded-lg bg-transparent px-1.5 py-1 text-[13px] leading-relaxed text-ink-muted transition-colors hover:bg-surface-soft focus:bg-surface-soft focus:text-ink-soft focus:outline-none"
          />

          <ul className="mt-1.5 flex flex-col gap-0.5">
            {keyPoints.map((point, pointIndex) => (
              <li key={pointIndex} className="flex items-center gap-2">
                <span className="size-1.5 shrink-0 rounded-full bg-accent/70" />
                <input
                  aria-label={`第 ${index + 1} 页要点 ${pointIndex + 1}`}
                  value={point}
                  maxLength={200}
                  onChange={(event) => changePoint(pointIndex, event.target.value)}
                  className="min-w-0 flex-1 rounded-lg bg-transparent px-1.5 py-1 text-[13px] text-ink-soft transition-colors hover:bg-surface-soft focus:bg-surface-soft focus:outline-none"
                />
                {keyPoints.length > MIN_KEY_POINTS && (
                  <button
                    type="button"
                    aria-label={`删除第 ${index + 1} 页要点 ${pointIndex + 1}`}
                    onClick={() =>
                      onChange({
                        ...page,
                        key_points: keyPoints.filter((_, i) => i !== pointIndex),
                      })
                    }
                    className="grid size-5 shrink-0 place-items-center rounded-md text-ink-muted/70 transition-all hover:bg-surface-soft hover:text-negative"
                  >
                    <X className="size-3" />
                  </button>
                )}
              </li>
            ))}
          </ul>

          {keyPoints.length < MAX_KEY_POINTS && (
            <button
              type="button"
              onClick={() => onChange({ ...page, key_points: [...keyPoints, ''] })}
              className="mt-1 ml-3.5 text-xs text-ink-muted transition-colors hover:text-accent"
            >
              + 要点
            </button>
          )}
        </div>

        {canRemove && (
          <button
            type="button"
            aria-label={`删除第 ${index + 1} 页`}
            onClick={onRemove}
            className="grid size-7 shrink-0 place-items-center rounded-lg text-ink-muted/70 transition-all hover:bg-negative/8 hover:text-negative"
          >
            <Trash2 className="size-3.5" />
          </button>
        )}
      </div>
    </li>
  )
}

/** 大纲改动自动落库；同一时刻只允许一个保存在飞，避免 revision 撞车 */
function useAutosave({
  revision,
  pages,
  pageCount,
  dirty,
  draftingPoint,
  enabled,
  save,
  saving,
}: {
  revision: number
  pages: OutlinePage[]
  pageCount: number
  dirty: boolean
  draftingPoint: boolean
  enabled: boolean
  save: (input: { revision: number; pages: OutlinePage[] }) => void | Promise<void>
  saving: boolean
}): string {
  const savedOnceRef = useRef(false)
  const saveRef = useRef(save)
  saveRef.current = save

  useEffect(() => {
    if (!dirty || !enabled || saving) return
    const timer = window.setTimeout(() => {
      savedOnceRef.current = true
      void saveRef.current({ revision, pages: normalizePages(pages) })
    }, 900)
    return () => window.clearTimeout(timer)
  }, [dirty, enabled, saving, pages, revision, pageCount])

  if (saving) return '保存中…'
  if (dirty && draftingPoint) return '编辑中…'
  if (dirty) return '待保存'
  return savedOnceRef.current ? '已保存' : ''
}

function Shell({
  title,
  meta,
  actions,
  children,
}: {
  title: string
  meta?: ReactNode
  actions?: ReactNode
  children: ReactNode
}) {
  return (
    <div className="flex min-h-screen flex-col">
      <WorkbenchHeader title={title} meta={meta}>
        {actions}
      </WorkbenchHeader>
      <div className="bg-aurora flex-1">{children}</div>
    </div>
  )
}

function CenterCard({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto max-w-lg px-6 py-24">
      <div className="rounded-3xl border border-line bg-surface px-8 py-10 text-center shadow-card">
        {children}
      </div>
    </div>
  )
}

/** 新页给可用的占位内容而不是空白：空标题、空目标在服务端是非法的 */
function blankPage(index: number): OutlinePage {
  return {
    id: crypto.randomUUID(),
    title: `第 ${index} 页`,
    objective: '这一页要说明的结论',
    key_points: ['要点一', '要点二'],
    source_refs: [],
    layout_id: 'bullets',
    page_role: 'content',
  }
}

/** 去掉空白要点再落库，避免生成时出现空条目 */
function normalizePages(pages: OutlinePage[]): OutlinePage[] {
  return pages.map((page) => ({
    ...page,
    title: page.title.trim(),
    objective: page.objective.trim(),
    key_points: page.key_points.map((point) => point.trim()).filter((point) => point.length > 0),
  }))
}

function pageIncomplete(page: OutlinePage): boolean {
  const points = page.key_points.filter((point) => point.trim().length > 0)
  return page.title.trim().length === 0 || page.objective.trim().length === 0 || points.length < MIN_KEY_POINTS
}
