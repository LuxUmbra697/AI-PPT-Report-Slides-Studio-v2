import { MoreHorizontal, Plus, Sparkles, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { StatusPill } from '@/components/StatusPill'
import { Button } from '@/components/ui/Button'
import { useDeleteProject, useProjects } from '@/features/projects/api'
import type { Project } from '@/features/projects/types'
import { relativeTime } from '@/lib/datetime'
import { errorMessage } from '@/lib/errors'
import { ThemeCover } from '@/render/ThemeCover'
import { resolveTheme, type ThemeOverrides } from '@/render/themeOverrides'

export default function ProjectsPage() {
  const navigate = useNavigate()
  const projects = useProjects()
  const remove = useDeleteProject()

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">我的 PPT</h1>
        <p className="mt-1.5 text-sm text-ink-muted">固定 16:9 画幅，导出为原生可编辑 PPTX</p>
      </div>

      {projects.isPending && <CardSkeletonGrid />}

      {projects.isError && (
        <p role="alert" className="rounded-2xl bg-negative/8 px-5 py-4 text-sm text-negative">
          {errorMessage(projects.error, 'PPT 列表加载失败，请稍后重试')}
        </p>
      )}

      {projects.data?.length === 0 && <EmptyState onCreate={() => navigate('/create')} />}

      {projects.data && projects.data.length > 0 && (
        <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {projects.data.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              deleting={remove.isPending && remove.variables === project.id}
              onDelete={() => remove.mutate(project.id)}
            />
          ))}
        </ul>
      )}

      {remove.isError && (
        <p role="alert" className="mt-5 text-sm text-negative">
          {errorMessage(remove.error, '删除失败，请稍后重试')}
        </p>
      )}
    </div>
  )
}

function ProjectCard({
  project,
  deleting,
  onDelete,
}: {
  project: Project
  deleting: boolean
  onDelete: () => void
}) {
  const theme = resolveTheme(
    project.theme_id,
    (project.theme_overrides ?? {}) as ThemeOverrides,
  )

  return (
    <li className="group relative">
      <Link
        to={`/projects/${project.id}`}
        className="block overflow-hidden rounded-2xl border border-line bg-surface transition-all duration-200 hover:-translate-y-0.5 hover:border-line-strong hover:shadow-card"
      >
        <div className="border-b border-line">
          <ThemeCover theme={theme} title={project.title} />
        </div>
        <div className="flex flex-col gap-2.5 px-4 py-3.5">
          <p className="truncate pr-8 text-[15px] font-semibold tracking-tight">{project.title}</p>
          <div className="flex items-center gap-2 text-xs text-ink-muted">
            <StatusPill status={project.status} />
            <span>{project.page_count} 页</span>
            <span aria-hidden>·</span>
            <span>{relativeTime(project.updated_at)}</span>
          </div>
        </div>
      </Link>

      <CardMenu deleting={deleting} onDelete={onDelete} />
    </li>
  )
}

function CardMenu({ deleting, onDelete }: { deleting: boolean; onDelete: () => void }) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onPointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onPointer)
    return () => document.removeEventListener('mousedown', onPointer)
  }, [open])

  return (
    <div ref={rootRef} className="absolute right-3 bottom-3">
      <button
        type="button"
        aria-label="更多操作"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="grid size-7 place-items-center rounded-lg bg-surface/90 text-ink-muted shadow-sm ring-1 ring-line transition-all hover:bg-surface-soft hover:text-ink"
      >
        <MoreHorizontal className="size-4" />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 bottom-full z-20 mb-1 w-40 overflow-hidden rounded-xl border border-line bg-surface shadow-pop"
        >
          <button
            type="button"
            role="menuitem"
            disabled={deleting}
            onClick={() => {
              setOpen(false)
              onDelete()
            }}
            className="flex w-full items-center gap-2 px-3.5 py-2.5 text-[13px] text-negative transition-colors hover:bg-negative/8 disabled:opacity-50"
          >
            <Trash2 className="size-3.5" />
            {deleting ? '删除中…' : '删除'}
          </button>
        </div>
      )}
    </div>
  )
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="rounded-3xl border border-dashed border-line-strong bg-aurora px-8 py-20 text-center">
      <span className="mx-auto mb-5 grid size-12 place-items-center rounded-2xl bg-surface text-accent shadow-card">
        <Sparkles className="size-5" />
      </span>
      <h2 className="text-xl font-semibold tracking-tight">还没有 PPT</h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-ink-muted">
        给一个主题，或者把已有的文字、文档交给它，先看大纲，再生成可编辑的 16:9 页面。
      </p>
      <Button size="lg" onClick={onCreate} className="mt-7">
        <Plus className="size-4" />
        新建 PPT
      </Button>
    </div>
  )
}

function CardSkeletonGrid() {
  return (
    <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
      {[0, 1, 2].map((key) => (
        <div key={key} className="overflow-hidden rounded-2xl border border-line bg-surface">
          <div className="aspect-video animate-pulse bg-surface-soft" />
          <div className="flex flex-col gap-2.5 px-4 py-3.5">
            <div className="h-4 w-2/3 animate-pulse rounded bg-surface-soft" />
            <div className="h-3 w-1/3 animate-pulse rounded bg-surface-soft" />
          </div>
        </div>
      ))}
    </div>
  )
}
