import { useMutation } from '@tanstack/react-query'
import { useGenerateDeck } from '@/features/deck/api'
import { useConfirmOutline, useUpdateOutline } from '@/features/outline/api'
import type { OutlinePage } from '@/features/outline/types'
import { useUpdateProject } from '@/features/projects/api'

interface LaunchInput {
  revision: number
  /** 有未保存的改动时先落库：确认校验的是服务端的大纲 */
  pages?: OutlinePage[]
  /** 与当前项目主题不同时才提交 */
  themeId?: string
}

/**
 * 「生成 PPT」这一次点击背后的完整链路：存大纲 → 定主题 → 确认 → 起生成任务。
 *
 * 合成一个动作而不是让用户依次点四个按钮，是因为这四步对用户是同一个意图；
 * 拆开只会让中间态（已确认但没生成）暴露出来，而那个状态没人想停留。
 */
export function useConfirmAndGenerate(projectId: string) {
  const updateOutline = useUpdateOutline(projectId)
  const updateProject = useUpdateProject(projectId)
  const confirm = useConfirmOutline(projectId)
  const generate = useGenerateDeck(projectId)

  return useMutation({
    mutationFn: async ({ revision, pages, themeId }: LaunchInput) => {
      let current = revision

      if (pages) {
        const saved = await updateOutline.mutateAsync({ revision, pages })
        current = saved.revision
      }
      // 主题不参与大纲输入指纹，可以在确认前安全落库
      if (themeId) await updateProject.mutateAsync({ theme_id: themeId })

      const confirmed = await confirm.mutateAsync(current)
      await generate.mutateAsync({ regenerateAll: false })
      return confirmed
    },
  })
}
