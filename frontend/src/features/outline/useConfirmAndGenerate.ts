import { useMutation } from '@tanstack/react-query'
import { useGenerateDeck } from '@/features/deck/api'
import { useGenerateHtmlReport } from '@/features/html-report/api'
import { useConfirmOutline, useUpdateOutline } from '@/features/outline/api'
import type { OutlinePage } from '@/features/outline/types'
import { useUpdateProject } from '@/features/projects/api'

interface LaunchInput {
  revision: number
  /** 有未保存的改动时先落库：确认校验的是服务端的大纲 */
  pages?: OutlinePage[]
  /** 与当前项目主题不同时才提交 */
  themeId?: string
  /** Template/ 外部模板的选择；null 表示明确取消外部模板。 */
  externalTemplateId?: string | null
}

/**
 * 确认后的链路按项目交付物分叉：PPT 才起 deck 任务，HTML 直接起报告正文任务。
 *
 * 合成一个动作而不是让用户依次点四个按钮，是因为这四步对用户是同一个意图；
 * 拆开只会让中间态（已确认但没生成）暴露出来，而那个状态没人想停留。
 */
export function useConfirmAndGenerate(projectId: string, outputFormat: 'ppt' | 'html') {
  const updateOutline = useUpdateOutline(projectId)
  const updateProject = useUpdateProject(projectId)
  const confirm = useConfirmOutline(projectId)
  const generate = useGenerateDeck(projectId)
  const generateHtmlReport = useGenerateHtmlReport(projectId)

  return useMutation({
    mutationFn: async ({ revision, pages, themeId, externalTemplateId }: LaunchInput) => {
      let current = revision

      if (pages) {
        const saved = await updateOutline.mutateAsync({ revision, pages })
        current = saved.revision
      }
      // 主题不参与大纲输入指纹，可以在确认前安全落库
      if (themeId || externalTemplateId !== undefined) {
        await updateProject.mutateAsync({
          ...(themeId ? { theme_id: themeId } : {}),
          ...(externalTemplateId !== undefined ? { external_template_id: externalTemplateId } : {}),
        })
      }

      const confirmed = await confirm.mutateAsync(current)
      if (outputFormat === 'html') {
        await generateHtmlReport.mutateAsync(false)
      } else {
        await generate.mutateAsync({ regenerateAll: false })
      }
      return confirmed
    },
  })
}
