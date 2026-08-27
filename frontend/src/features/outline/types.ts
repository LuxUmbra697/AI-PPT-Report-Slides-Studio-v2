import type { components } from '@/api/schema'

type Schemas = components['schemas']

export type Outline = Schemas['OutlinePublic']
export type OutlinePage = Schemas['OutlinePage']
export type OutlineUpdate = Schemas['OutlineUpdate']
export type OutlineGenerateAccepted = Schemas['OutlineGenerateAccepted']

export interface OutlineProgressEvent {
  type: 'snapshot' | 'progress' | 'completed' | 'failed'
  status: Outline['status']
  progress: number
  message: string
  revision?: number | null
}
