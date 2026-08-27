import { useQueryClient } from '@tanstack/react-query'
import { deckKey } from '@/features/deck/api'
import type { DeckProgressEvent } from '@/features/deck/types'
import { useEventStream } from '@/hooks/useEventStream'

const TERMINAL_TYPES = ['completed', 'cancelled', 'failed'] as const
const projectKey = (projectId: string) => ['projects', projectId] as const

export function useDeckProgress(projectId: string, active: boolean) {
  const queryClient = useQueryClient()

  return useEventStream<DeckProgressEvent>({
    path: `/projects/${projectId}/deck/events`,
    active,
    terminalTypes: TERMINAL_TYPES,
    // 页面内容不走推送，事件只负责触发重拉；项目状态也要跟着刷，
    // 否则生成结束后 project.status 仍停在 generating，顶栏会卡在「取消生成」。
    onEvent: () => {
      void queryClient.invalidateQueries({ queryKey: deckKey(projectId) })
      void queryClient.invalidateQueries({ queryKey: projectKey(projectId) })
    },
  })
}
