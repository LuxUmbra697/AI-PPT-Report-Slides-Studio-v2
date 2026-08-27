import { Loader2 } from 'lucide-react'
import { Link, useParams } from 'react-router'
import { EditorWorkspace } from '@/features/deck/EditorWorkspace'
import { useOutline } from '@/features/outline/api'
import { OutlineWorkspace } from '@/features/outline/OutlineWorkspace'
import { useProject } from '@/features/projects/api'

/**
 * 一个 PPT 只有两个阶段：确认大纲，或在画布上编辑。
 * 阶段以大纲状态为准而不是项目状态：页面开始生成后项目状态会变，
 * 但用户该待的地方始终是编辑工作台。
 */
export default function ProjectDetailPage() {
  const { projectId = '' } = useParams()
  const project = useProject(projectId)
  const outline = useOutline(projectId)

  if (project.isPending || outline.isPending) {
    return (
      <div className="grid min-h-screen place-items-center">
        <Loader2 className="size-5 animate-spin text-ink-muted" />
      </div>
    )
  }

  if (project.isError || !project.data) {
    return (
      <div className="grid min-h-screen place-items-center px-6">
        <div className="rounded-3xl border border-line bg-surface px-8 py-10 text-center shadow-card">
          <p className="text-sm text-ink-soft">这个 PPT 不存在，或你没有访问权限。</p>
          <Link
            to="/projects"
            className="mt-4 inline-block text-sm font-medium text-accent underline-offset-2 hover:underline"
          >
            返回我的 PPT
          </Link>
        </div>
      </div>
    )
  }

  return outline.data?.status === 'confirmed' ? (
    <EditorWorkspace project={project.data} />
  ) : (
    <OutlineWorkspace project={project.data} />
  )
}
