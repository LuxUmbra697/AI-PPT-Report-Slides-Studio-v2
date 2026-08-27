import type { components } from '@/api/schema'

type Schemas = components['schemas']

export type Project = Schemas['ProjectPublic']
export type ProjectDetail = Schemas['ProjectDetail']
export type ProjectCreate = Schemas['ProjectCreate']
export type ProjectUpdate = Schemas['ProjectUpdate']
export type ProjectSource = Schemas['SourcePublic']
export type Tone = ProjectCreate['tone']

export const TONE_LABEL: Record<NonNullable<Tone>, string> = {
  professional: '专业严谨',
  plain: '通俗易懂',
  punchy: '简洁有力',
}

export const PAGE_COUNT_RANGE = { min: 5, max: 20 } as const
export const ACCEPTED_UPLOAD = '.pdf,.docx,.md,.markdown,.txt'
