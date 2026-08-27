import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { request } from '@/api/client'
import { deckKey } from '@/features/deck/api'
import type {
  Project,
  ProjectCreate,
  ProjectDetail,
  ProjectSource,
  ProjectUpdate,
} from '@/features/projects/types'
import type { ThemeOverrides } from '@/render/themeOverrides'

const listKey = ['projects'] as const
const detailKey = (id: string) => ['projects', id] as const

export function useProjects() {
  return useQuery({
    queryKey: listKey,
    queryFn: () => request<Project[]>('/projects'),
  })
}

export function useProject(id: string) {
  return useQuery({
    queryKey: detailKey(id),
    queryFn: () => request<ProjectDetail>(`/projects/${id}`),
  })
}

export function useUpdateProject(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ProjectUpdate) =>
      request<ProjectDetail>(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
    onSuccess: (project) => {
      queryClient.setQueryData(detailKey(id), project)
      void queryClient.invalidateQueries({ queryKey: listKey })
    },
  })
}

export function useUpdateProjectTheme(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { theme_id?: string; overrides?: ThemeOverrides }) =>
      request<ProjectDetail>(`/projects/${id}/theme`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      }),
    onSuccess: (project) => {
      queryClient.setQueryData(detailKey(id), project)
      void queryClient.invalidateQueries({ queryKey: listKey })
      // 字号变化会重算 issues，刷新 deck 缓存
      void queryClient.invalidateQueries({ queryKey: deckKey(id) })
    },
  })
}

export function useDeleteProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => request<void>(`/projects/${id}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: listKey }),
  })
}

export type DraftMode = 'topic' | 'text' | 'document'

export interface DraftInput {
  mode: DraftMode
  /** topic / text 模式的正文；document 模式忽略 */
  content: string
  files: File[]
  title: string
  audience: string | null
  tone: NonNullable<ProjectCreate['tone']>
  pageCount: number
  themeId: string
  layoutMode?: 'fixed' | 'flex'
  contentDensity?: 'concise' | 'medium' | 'detailed'
  onStep?: (step: string) => void
}

/**
 * 创作单屏的唯一提交动作：建项目 → attach 素材 → 起大纲任务。
 *
 * 三步任何一步失败都把项目删掉：用户只按了一次"生成大纲"，
 * 半成品草稿留在列表里既解释不清也无法自愈（界面上已不提供补素材入口）。
 */
export function useCreateDraft() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (input: DraftInput): Promise<ProjectDetail> => {
      input.onStep?.('正在创建 PPT…')
      const project = await request<ProjectDetail>('/projects', {
        method: 'POST',
        body: JSON.stringify({
          title: input.title,
          audience: input.audience,
          tone: input.tone,
          page_count: input.pageCount,
          theme_id: input.themeId,
          layout_mode: input.layoutMode ?? 'flex',
          content_density: input.contentDensity ?? 'medium',
        }),
      })

      try {
        if (input.mode === 'document') {
          for (const [index, file] of input.files.entries()) {
            input.onStep?.(`正在读取文档（${index + 1}/${input.files.length}）…`)
            const form = new FormData()
            form.append('file', file)
            await request<ProjectSource>(`/projects/${project.id}/sources/upload`, {
              method: 'POST',
              body: form,
            })
          }
        } else {
          input.onStep?.('正在整理内容…')
          await request<ProjectSource>(`/projects/${project.id}/sources`, {
            method: 'POST',
            body: JSON.stringify({ kind: input.mode, content: input.content }),
          })
        }

        input.onStep?.('正在生成大纲…')
        await request(`/projects/${project.id}/outline/generate`, { method: 'POST' })
      } catch (error) {
        await request<void>(`/projects/${project.id}`, { method: 'DELETE' }).catch(() => {})
        throw error
      }

      return project
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: listKey }),
  })
}
