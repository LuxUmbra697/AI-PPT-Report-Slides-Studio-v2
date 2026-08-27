import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, request } from '@/api/client'
import type {
  Outline,
  OutlineGenerateAccepted,
  OutlineUpdate,
} from '@/features/outline/types'

export const outlineKey = (projectId: string) => ['projects', projectId, 'outline'] as const
const projectKey = (projectId: string) => ['projects', projectId] as const
const projectListKey = ['projects'] as const

export function useOutline(projectId: string) {
  return useQuery({
    queryKey: outlineKey(projectId),
    queryFn: async () => {
      try {
        return await request<Outline>(`/projects/${projectId}/outline`)
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null
        throw error
      }
    },
    retry: false,
  })
}

export function useGenerateOutline(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () =>
      request<OutlineGenerateAccepted>(`/projects/${projectId}/outline/generate`, {
        method: 'POST',
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: outlineKey(projectId) }),
  })
}

export function useUpdateOutline(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: OutlineUpdate) =>
      request<Outline>(`/projects/${projectId}/outline`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      }),
    onSuccess: (outline) => queryClient.setQueryData(outlineKey(projectId), outline),
  })
}

function useRevisionMutation(projectId: string, action: 'confirm') {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (revision: number) =>
      request<Outline>(`/projects/${projectId}/outline/${action}`, {
        method: 'POST',
        body: JSON.stringify({ revision }),
      }),
    onSuccess: (outline) => {
      queryClient.setQueryData(outlineKey(projectId), outline)
      void queryClient.invalidateQueries({ queryKey: projectKey(projectId) })
      void queryClient.invalidateQueries({ queryKey: projectListKey })
    },
  })
}

export function useConfirmOutline(projectId: string) {
  return useRevisionMutation(projectId, 'confirm')
}
