import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { request, requestBinary } from '@/api/client'
import type { components } from '@/api/schema'

type Schemas = components['schemas']
export type HtmlReport = Schemas['HtmlReportPublic']

export const htmlReportKey = (projectId: string) => ['projects', projectId, 'html-report'] as const
const projectKey = (projectId: string) => ['projects', projectId] as const
const htmlReportPreviewKey = (projectId: string, jobId?: string | null) =>
  [...htmlReportKey(projectId), 'render', jobId ?? 'latest'] as const

export function useHtmlReport(projectId: string) {
  return useQuery({
    queryKey: htmlReportKey(projectId),
    queryFn: () => request<HtmlReport>(`/projects/${projectId}/html-report`),
    refetchInterval: (query) => (query.state.data?.status === 'generating' ? 1200 : false),
  })
}

export function useGenerateHtmlReport(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (regenerate: boolean = false) =>
      request<HtmlReport>(`/projects/${projectId}/html-report/generate`, {
        method: 'POST',
        body: JSON.stringify({ regenerate }),
      }),
    onSuccess: (report) => {
      queryClient.setQueryData(htmlReportKey(projectId), report)
      // 报告重新生成后，不能让 iframe 继续复用上一轮的 HTML 字符串。
      queryClient.removeQueries({ queryKey: [...htmlReportKey(projectId), 'render'] })
      void queryClient.invalidateQueries({ queryKey: projectKey(projectId) })
    },
  })
}

export function useHtmlReportPreview(
  projectId: string,
  jobId: string | null | undefined,
  enabled: boolean,
) {
  return useQuery({
    // 每一轮报告都用独立缓存键；ready 之后才能取预览，因此不会提前请求。
    queryKey: htmlReportPreviewKey(projectId, jobId),
    queryFn: async () => {
      const response = await requestBinary(`/projects/${projectId}/html-report/render`)
      return response.text()
    },
    enabled,
    staleTime: 0,
    refetchOnMount: 'always',
  })
}
