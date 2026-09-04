import { Loader2 } from 'lucide-react'
import { Link, useParams } from 'react-router'
import { EditorWorkspace } from '@/features/deck/EditorWorkspace'
import { HtmlReportWorkspace } from '@/features/html-report/HtmlReportWorkspace'
import { useOutline } from '@/features/outline/api'
import { OutlineWorkspace } from '@/features/outline/OutlineWorkspace'
import { useProject } from '@/features/projects/api'

/**
 * 项目先确认大纲；随后按交付物进入 PPT 画布或 HTML 报告工作区。
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
          <p className="text-sm text-ink-soft">这个项目不存在，或你没有访问权限。</p>
          <Link
            to="/projects"
            className="mt-4 inline-block text-sm font-medium text-accent underline-offset-2 hover:underline"
          >
            返回我的创作
          </Link>
        </div>
      </div>
    )
  }

  if (outline.data?.status !== 'confirmed') {
    return <OutlineWorkspace project={project.data} />
  }

  return project.data.output_format === 'html' ? (
    <HtmlReportWorkspace project={project.data} />
  ) : (
    <EditorWorkspace project={project.data} />
  )
}
