import type { components } from '@/api/schema'
import type { FlexContainer } from '@/render/flexLayout'
import type { Block, ImageBlock, Slide } from '@/render/types'

type Schemas = components['schemas']

export const ACCEPTED_IMAGE = 'image/png,image/jpeg,image/webp'

/**
 * 布局树统一用渲染器侧的 FlexContainer。
 * schema 生成的版本把 gap_pt / grow 标成必填，而编辑器构造出的树可以省略它们，
 * 两套同名类型混用会让赋值不兼容（tsc -b 报 "Two different types with this name"）。
 * blocks 用渲染侧本地 Block 联合（含 Cards/Callout），与编辑提交类型同文件维护。
 */
export type DeckSlide = Omit<Schemas['SlidePublic'], 'layout_tree' | 'blocks'> & {
  layout_tree?: FlexContainer | null
  blocks: Block[]
}
export type Deck = Omit<Schemas['DeckPublic'], 'slides'> & {
  slides: DeckSlide[]
}
export type DeckStatus = Deck['status']
/** 整页增删复制的响应：整份 deck + 操作后应选中的页 */
export type DeckPageResult = Omit<Schemas['DeckPageResult'], 'deck'> & {
  deck: Deck
}
export type DeckGenerateAccepted = Schemas['DeckGenerateAccepted']
export type LayoutCandidate = Schemas['LayoutCandidatePublic']
export type AiEditProposal = Schemas['AiEditProposalPublic']
export type AiEditOperation = Schemas['AiEditOperationPublic']
export type StructureIssue = Schemas['StructureIssue']
export type ExportCheckReport = Schemas['ExportCheckReport']

/**
 * relayout 候选的本地契约：layout_tree 用渲染侧 FlexContainer（可省略 gap_pt/grow），
 * 与 schema RelayoutCandidate 的强制必填版区分。
 */
export interface RelayoutCandidate {
  id: string
  layout_tree: FlexContainer
}
export interface RelayoutProposal {
  revision: number
  candidates: RelayoutCandidate[]
}
/** 导出回读验证问题：OpenAPI 未覆盖，字段与后端 VerifyIssue 对齐 */
export interface ExportVerifyIssue {
  check: string
  slide_index: number | null
  shape: string | null
  message: string
}
export type ChartBlockUpdate = {
  type: 'chart'
  revision: number
  chart_type: 'bar' | 'column' | 'line' | 'pie'
  categories: string[]
  series: Array<{ name: string; values: number[] }>
  unit?: string | null
}

export type CardsBlockUpdate = {
  type: 'cards'
  revision: number
  items: Array<{ title: string; desc: string; icon?: string | null }>
}

export type CalloutBlockUpdate = {
  type: 'callout'
  revision: number
  text: string
  icon?: string | null
  variant: 'note' | 'source'
}

/** Omit 不会自动分发联合类型，需逐个剥掉 revision */
export type BlockUpdateBody =
  | Omit<Schemas['TextBlockUpdate'], 'revision'>
  | Omit<Schemas['BulletsBlockUpdate'], 'revision'>
  | Omit<Schemas['KpiBlockUpdate'], 'revision'>
  | Omit<Schemas['TableBlockUpdate'], 'revision'>
  | Omit<ChartBlockUpdate, 'revision'>
  | Omit<CardsBlockUpdate, 'revision'>
  | Omit<CalloutBlockUpdate, 'revision'>

export interface DeckProgressEvent {
  type:
    | 'snapshot'
    | 'slide_started'
    | 'slide_completed'
    | 'slide_failed'
    | 'completed'
    | 'cancelled'
    | 'failed'
  status: DeckStatus
  progress: number
  message: string
  slide_id?: string | null
  position?: number | null
  ready: number
  failed: number
  total: number
}

export function imageBlocks(slide: DeckSlide): ImageBlock[] {
  return slide.blocks.filter((block): block is ImageBlock => block.type === 'image')
}

/** 胶片标题优先用画布上的 title 槽，避免改字后侧栏仍显示大纲旧标题 */
export function slideDisplayTitle(slide: DeckSlide): string {
  const title = slide.blocks.find(
    (block) => block.type === 'text' && block.slot_id === 'title',
  )
  const text = title?.type === 'text' ? title.text.trim() : ''
  return text || slide.title
}

/** 落库的页面转成渲染器认识的内容模型：两者字段同源，只是多了生成状态 */
export function toRenderSlide(slide: DeckSlide): Slide {
  return {
    id: slide.id,
    layout_id: slide.layout_id,
    layout_mode: slide.layout_mode,
    layout_tree: slide.layout_tree,
    blocks: slide.blocks,
    speaker_notes: slide.speaker_notes,
    revision: slide.revision,
  }
}
