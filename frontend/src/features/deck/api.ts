import { type QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { request, requestBinary } from '@/api/client'
import { replaceSlideInDeck, replaceSlidesInDeck } from '@/features/deck/cache'
import type { FlexBlockType } from '@/features/deck/flexTree'
import type {
  AiEditProposal,
  BlockUpdateBody,
  Deck,
  DeckGenerateAccepted,
  DeckPageResult,
  DeckSlide,
  ExportCheckReport,
  LayoutCandidate,
  RelayoutProposal,
} from '@/features/deck/types'
import { outlineKey } from '@/features/outline/api'
import { filenameFromDisposition, saveBlob } from '@/lib/download'
import type { BlockStyle } from '@/render/blockStyle'
import type { FlexContainer } from '@/render/flexLayout'

export const deckKey = (projectId: string) => ['projects', projectId, 'deck'] as const
const projectKey = (projectId: string) => ['projects', projectId] as const
const slideLayoutsKey = (projectId: string, slideId: string) =>
  ['projects', projectId, 'deck', 'slides', slideId, 'layouts'] as const
export const deckQualityKey = (projectId: string) =>
  ['projects', projectId, 'deck', 'quality'] as const

/**
 * 单页更新后写回 deck 缓存。
 *
 * 用 setQueryData 而不是 invalidate，是为了不冲掉正在编辑的 DOM；
 * 但质量报告依赖页面内容，必须跟着失效，否则用户改完问题仍看到旧报告。
 */
export function commitSlideToCache(
  queryClient: QueryClient,
  projectId: string,
  slide: DeckSlide,
) {
  queryClient.setQueryData<Deck>(deckKey(projectId), (current) =>
    replaceSlideInDeck(current, slide),
  )
  void queryClient.invalidateQueries({ queryKey: deckQualityKey(projectId) })
}

export function useDeck(projectId: string, enabled = true) {
  return useQuery({
    queryKey: deckKey(projectId),
    queryFn: () => request<Deck>(`/projects/${projectId}/deck`),
    enabled,
  })
}

/** 写操作共用：路径与请求体由调用方提供，成功后刷新页面列表与项目状态 */
function useDeckMutation<TVariables>(
  projectId: string,
  toRequest: (variables: TVariables) => { path: string; body?: unknown },
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (variables: TVariables) => {
      const { path, body } = toRequest(variables)
      return request<DeckGenerateAccepted | null>(path, {
        method: 'POST',
        body: body === undefined ? undefined : JSON.stringify(body),
      })
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: deckKey(projectId) })
      void queryClient.invalidateQueries({ queryKey: projectKey(projectId) })
    },
  })
}

export function useGenerateDeck(projectId: string) {
  return useDeckMutation<{ regenerateAll: boolean }>(projectId, ({ regenerateAll }) => ({
    path: `/projects/${projectId}/deck/generate`,
    body: { regenerate_all: regenerateAll },
  }))
}

export function useRetrySlide(projectId: string) {
  return useDeckMutation<string>(projectId, (slideId) => ({
    path: `/projects/${projectId}/deck/slides/${slideId}/retry`,
  }))
}

export function useCancelDeck(projectId: string) {
  return useDeckMutation<void>(projectId, () => ({
    path: `/projects/${projectId}/deck/cancel`,
  }))
}

interface ReplaceImageInput {
  slideId: string
  blockId: string
  revision: number
  file: File
}

export function useReplaceSlideImage(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ slideId, blockId, revision, file }: ReplaceImageInput) => {
      const form = new FormData()
      form.append('file', file)
      // 带上版本号：换图期间这一页可能刚被 AI 改过，冲突要由服务端判定
      form.append('revision', String(revision))
      return request<DeckSlide>(
        `/projects/${projectId}/deck/slides/${slideId}/blocks/${blockId}/image`,
        { method: 'PUT', body: form },
      )
    },
    onSuccess: (slide) => commitSlideToCache(queryClient, projectId, slide),
  })
}

export function updateSlideBlock(
  projectId: string,
  slideId: string,
  blockId: string,
  body: BlockUpdateBody & { revision: number },
) {
  return request<DeckSlide>(
    `/projects/${projectId}/deck/slides/${slideId}/blocks/${blockId}`,
    { method: 'PATCH', body: JSON.stringify(body) },
  )
}

export function updateSlideBlockStyle(
  projectId: string,
  slideId: string,
  blockId: string,
  body: { revision: number; style: BlockStyle | null },
) {
  return request<DeckSlide>(
    `/projects/${projectId}/deck/slides/${slideId}/blocks/${blockId}/style`,
    { method: 'PATCH', body: JSON.stringify(body) },
  )
}

export function useReorderSlides(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (slideIds: string[]) =>
      request<DeckSlide[]>(`/projects/${projectId}/deck/slides/order`, {
        method: 'PUT',
        body: JSON.stringify({ slide_ids: slideIds }),
      }),
    onMutate: async (slideIds) => {
      await queryClient.cancelQueries({ queryKey: deckKey(projectId) })
      const previous = queryClient.getQueryData<Deck>(deckKey(projectId))
      if (previous) {
        const byId = new Map(previous.slides.map((slide) => [slide.id, slide]))
        const slides = slideIds.flatMap((id, index) => {
          const slide = byId.get(id)
          return slide ? [{ ...slide, position: index + 1 }] : []
        })
        queryClient.setQueryData<Deck>(deckKey(projectId), { ...previous, slides })
      }
      return { previous }
    },
    onError: (_error, _slideIds, context) => {
      if (context?.previous) {
        queryClient.setQueryData(deckKey(projectId), context.previous)
      }
    },
    onSuccess: (slides) => {
      queryClient.setQueryData<Deck>(deckKey(projectId), (current) =>
        replaceSlidesInDeck(current, slides),
      )
      // 页序参与页面重复判定，排序后报告同样要重算
      void queryClient.invalidateQueries({ queryKey: deckQualityKey(projectId) })
    },
  })
}

/**
 * 整页增删复制：响应里带整份 deck，直接换掉缓存。
 *
 * 后端同一事务里还改了 page_count 与大纲页列表，所以项目详情与大纲也要失效。
 * 项目的 key 是 deck key 的前缀，必须 exact，否则会顺带把刚写进去的 deck 冲掉。
 */
function useDeckPageMutation<TVariables>(
  projectId: string,
  toRequest: (variables: TVariables) => {
    path: string
    method: 'POST' | 'DELETE'
    body?: unknown
  },
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (variables: TVariables) => {
      const { path, method, body } = toRequest(variables)
      return request<DeckPageResult>(path, {
        method,
        body: body === undefined ? undefined : JSON.stringify(body),
      })
    },
    onSuccess: (result) => {
      queryClient.setQueryData(deckKey(projectId), result.deck)
      void queryClient.invalidateQueries({ queryKey: projectKey(projectId), exact: true })
      void queryClient.invalidateQueries({ queryKey: outlineKey(projectId) })
      void queryClient.invalidateQueries({ queryKey: deckQualityKey(projectId) })
    },
  })
}

/** afterSlideId 为 null 表示追加到末尾 */
export function useInsertSlide(projectId: string) {
  return useDeckPageMutation<string | null>(projectId, (afterSlideId) => ({
    path: `/projects/${projectId}/deck/slides`,
    method: 'POST',
    body: { after_slide_id: afterSlideId },
  }))
}

export function useDuplicateSlide(projectId: string) {
  return useDeckPageMutation<string>(projectId, (slideId) => ({
    path: `/projects/${projectId}/deck/slides/${slideId}/duplicate`,
    method: 'POST',
  }))
}

export function useDeleteSlide(projectId: string) {
  return useDeckPageMutation<string>(projectId, (slideId) => ({
    path: `/projects/${projectId}/deck/slides/${slideId}`,
    method: 'DELETE',
  }))
}

export function useSlideLayouts(projectId: string, slideId: string, enabled: boolean) {
  return useQuery({
    queryKey: slideLayoutsKey(projectId, slideId),
    queryFn: () =>
      request<LayoutCandidate[]>(`/projects/${projectId}/deck/slides/${slideId}/layouts`),
    enabled,
  })
}

export function useSwitchSlideLayout(projectId: string, slideId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { layout_id: string; revision: number }) =>
      request<DeckSlide>(`/projects/${projectId}/deck/slides/${slideId}/layout`, {
        method: 'PUT',
        body: JSON.stringify(body),
      }),
    onSuccess: (slide) => {
      commitSlideToCache(queryClient, projectId, slide)
      void queryClient.invalidateQueries({ queryKey: slideLayoutsKey(projectId, slideId) })
    },
  })
}

export function createSlideBlock(
  projectId: string,
  slideId: string,
  body: {
    revision: number
    type: FlexBlockType
    parent_id: string
    index?: number
  },
) {
  return request<DeckSlide>(`/projects/${projectId}/deck/slides/${slideId}/blocks`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function deleteSlideBlock(
  projectId: string,
  slideId: string,
  blockId: string,
  body: { revision: number },
) {
  return request<DeckSlide>(
    `/projects/${projectId}/deck/slides/${slideId}/blocks/${blockId}`,
    { method: 'DELETE', body: JSON.stringify(body) },
  )
}

export function updateFlexLayout(
  projectId: string,
  slideId: string,
  body: { revision: number; layout_tree: FlexContainer },
) {
  return request<DeckSlide>(
    `/projects/${projectId}/deck/slides/${slideId}/flex-layout`,
    { method: 'PUT', body: JSON.stringify(body) },
  )
}

export function updateFlexState(
  projectId: string,
  slideId: string,
  body: {
    revision: number
    blocks: DeckSlide['blocks']
    layout_tree: FlexContainer
  },
) {
  return request<DeckSlide>(
    `/projects/${projectId}/deck/slides/${slideId}/flex-state`,
    { method: 'PUT', body: JSON.stringify(body) },
  )
}

export function unlockSlideFlex(
  projectId: string,
  slideId: string,
  body: { revision: number },
) {
  return request<DeckSlide>(
    `/projects/${projectId}/deck/slides/${slideId}/unlock-flex`,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function useUnlockSlideFlex(projectId: string, slideId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { revision: number }) => unlockSlideFlex(projectId, slideId, body),
    onSuccess: (slide) => {
      commitSlideToCache(queryClient, projectId, slide)
      void queryClient.invalidateQueries({ queryKey: slideLayoutsKey(projectId, slideId) })
    },
  })
}

export function useProposeRelayout(projectId: string, slideId: string) {
  return useMutation({
    mutationFn: (body: { revision: number }) =>
      request<RelayoutProposal>(`/projects/${projectId}/deck/slides/${slideId}/relayout`, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  })
}

export function useProposeAiEdit(projectId: string, slideId: string) {
  return useMutation({
    mutationFn: (body: {
      revision: number
      instruction: string
      history?: Array<{ instruction: string; note?: string | null }>
    }) =>
      request<AiEditProposal>(`/projects/${projectId}/deck/slides/${slideId}/ai-edit`, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  })
}

export function useApplyAiEdit(projectId: string, slideId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: {
      revision: number
      op: 'replace' | 'add' | 'delete' | 'change_type'
      block_id: string
      after_block_id?: string | null
      side: 'before' | 'after'
      replace?: Record<string, unknown> | null
      block?: Record<string, unknown> | null
    }) =>
      request<DeckSlide>(`/projects/${projectId}/deck/slides/${slideId}/ai-edit/apply`, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    onSuccess: (slide) => commitSlideToCache(queryClient, projectId, slide),
  })
}

/** 仅在页面生成结束后拉取；生成中不请求，避免刷接口 */
export function useDeckQuality(projectId: string, enabled: boolean) {
  return useQuery({
    queryKey: deckQualityKey(projectId),
    queryFn: () => request<ExportCheckReport>(`/projects/${projectId}/deck/quality`),
    enabled,
  })
}

export function useExportDeck(projectId: string, fallbackName = 'export.pptx') {
  return useMutation({
    mutationFn: async () => {
      const response = await requestBinary(`/projects/${projectId}/deck/export`)
      const blob = await response.blob()
      const filename = filenameFromDisposition(
        response.headers.get('content-disposition'),
        fallbackName,
      )
      saveBlob(blob, filename)
    },
  })
}
