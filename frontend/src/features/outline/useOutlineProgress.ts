import { useQueryClient } from '@tanstack/react-query'
import { outlineKey } from '@/features/outline/api'
import type { OutlineProgressEvent } from '@/features/outline/types'
import { useEventStream } from '@/hooks/useEventStream'

const TERMINAL_TYPES = ['completed', 'failed'] as const

export function useOutlineProgress(projectId: string, active: boolean) {
  const queryClient = useQueryClient()

  return useEventStream<OutlineProgressEvent>({
    path: `/projects/${projectId}/outline/events`,
    active,
    terminalTypes: TERMINAL_TYPES,
    onEvent: (next) => {
      if (next.type === 'completed' || next.type === 'failed') {
        void queryClient.invalidateQueries({ queryKey: outlineKey(projectId) })
      }
    },
  })
}
