import { ChevronLeft } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'

/** 大纲页与编辑工作台共用的顶栏：返回、标题、右侧操作 */
export function WorkbenchHeader({
  title,
  meta,
  children,
}: {
  title: string
  meta?: ReactNode
  children?: ReactNode
}) {
  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-3 border-b border-line bg-surface/85 px-4 backdrop-blur-md">
      <Link
        to="/projects"
        aria-label="返回我的 PPT"
        className="grid size-8 shrink-0 place-items-center rounded-lg text-ink-muted transition-colors hover:bg-surface-soft hover:text-ink"
      >
        <ChevronLeft className="size-4.5" />
      </Link>

      <div className="flex min-w-0 items-center gap-3">
        <h1 className="truncate text-sm font-semibold tracking-tight">{title}</h1>
        {meta}
      </div>

      <div className="ml-auto flex items-center gap-2">{children}</div>
    </header>
  )
}
