import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { request } from '@/api/client'
import type { ThemeOverrides } from '@/render/themeOverrides'

export type TemplateAnalysisStatus =
  | 'not_analyzed'
  | 'ready'
  | 'partial'
  | 'unavailable'
  | 'failed'

export interface ExternalTemplate {
  id: string
  name: string
  filename: string
  source_path: string
  size_bytes: number
  modified_at: string
  slide_count: number
  layout_count: number
  image_count: number
  element_count: number
  background_count: number
  component_count: number
  text_preview: string[]
  palette: string[]
  fonts: string[]
  aspect_ratio: string
  structural_summary: string | null
  style_profile: {
    base_theme_id: string
    overrides: ThemeOverrides
  }
  analysis_status: TemplateAnalysisStatus
  style_summary: string | null
  image_summary: string | null
}

export interface ExternalTemplateRect {
  left: number
  top: number
  width: number
  height: number
}

export interface ExternalTemplateElement {
  id: string
  kind: string
  role: string
  name: string
  rect: ExternalTemplateRect
  z_index: number
  source_layer: 'master' | 'layout' | 'slide'
  text_preview: string | null
  colors: string[]
  asset_id: string | null
  is_background: boolean
}

export interface ExternalTemplateSlideInspection {
  slide_number: number
  elements: ExternalTemplateElement[]
}

export interface ExternalTemplateInspection {
  template_id: string
  slides: ExternalTemplateSlideInspection[]
}

export const externalTemplateKey = ['design', 'external-templates'] as const

export function useExternalTemplates() {
  return useQuery({
    queryKey: externalTemplateKey,
    queryFn: () => request<ExternalTemplate[]>('/design/external-templates'),
    staleTime: 30_000,
  })
}

export function useRefreshExternalTemplates() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () =>
      request<ExternalTemplate[]>('/design/external-templates/refresh', { method: 'POST' }),
    onSuccess: (templates) => queryClient.setQueryData(externalTemplateKey, templates),
  })
}

export function useExternalTemplateInspection(templateId: string | null | undefined) {
  return useQuery({
    queryKey: [...externalTemplateKey, templateId, 'inspection'] as const,
    queryFn: () =>
      request<ExternalTemplateInspection>(`/design/external-templates/${templateId}/inspection`),
    enabled: Boolean(templateId),
    staleTime: 5 * 60_000,
  })
}
