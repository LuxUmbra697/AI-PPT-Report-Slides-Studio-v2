import type { components } from '@/api/schema'
import type { AmbientMotif } from './ambient'
import type { FlexContainer } from './flexLayout'

type Schemas = components['schemas']

/**
 * 布局树以 flexLayout 里的 FlexContainer 为准：schema 生成的版本把 gap_pt / grow
 * 标成必填，而编辑器构造出的树可以省略它们，两套同名类型混用会让赋值不兼容。
 * blocks 用本地 Block 联合（含 Cards/Callout），与本文件 EditableBlockCommit 一并维护。
 */
export type Slide = Omit<Schemas['Slide'], 'layout_tree' | 'blocks'> & {
  layout_tree?: FlexContainer | null
  blocks: Block[]
}
export type Deck = Omit<Schemas['Deck'], 'slides'> & {
  slides: Slide[]
}
export type TextBlock = Schemas['TextBlock']
export type BulletsBlock = Schemas['BulletsBlock']
export type ImageBlock = Schemas['ImageBlock']
export type ChartBlock = Schemas['ChartBlock']
export type TableBlock = Schemas['TableBlock']
export type KpiBlock = Schemas['KpiBlock']

/** 本地块类型，字段与 backend content.py / OpenAPI 对齐 */
export type CardItem = {
  title: string
  desc: string
  icon?: string | null
}

export type CardsBlock = {
  id: string
  slot_id: string
  locked: boolean
  style?: Schemas['BlockStyle'] | null
  type: 'cards'
  items: CardItem[]
}

export type CalloutBlock = {
  id: string
  slot_id: string
  locked: boolean
  style?: Schemas['BlockStyle'] | null
  type: 'callout'
  text: string
  icon?: string | null
  variant: 'note' | 'source'
}

export type Block =
  | TextBlock
  | BulletsBlock
  | ImageBlock
  | ChartBlock
  | TableBlock
  | KpiBlock
  | CardsBlock
  | CalloutBlock

export type Layout = Schemas['Layout']
/** accepts 与本地 Block['type'] 对齐，避免与 schema 字面量联合漂移 */
export type Slot = Omit<Schemas['Slot'], 'accepts'> & {
  accepts: Array<Block['type']>
}
export type Decoration = Schemas['Decoration']
export type Rect = Schemas['Rect']

/**
 * 氛围层以 ambient.ts 里的 AmbientMotif 为准：schema 生成的版本把带默认值的
 * 字段标成必填，而 shared/themes/*.json 里这些字段本来就可以省略。
 */
export type Theme = Omit<Schemas['Theme'], 'ambient'> & { ambient?: AmbientMotif[] }
export type TextStyle = Schemas['TextStyle']
export type TextStyleName = NonNullable<Slot['text_style']>
/** 色令牌从 palette 键派生；TextStyle.color 放宽后可能是 hex */
export type ColorToken = Exclude<keyof Theme['palette'], 'chart_series'>

/** 16:9 基准画布，单位 pt。必须与后端 app/domain/geometry.py 保持一致 */
export const CANVAS_WIDTH_PT = 960
export const CANVAS_HEIGHT_PT = 540

/** 页面安全区：内容不贴画布边缘。必须与后端 geometry.py 的 SAFE_AREA 一致 */
export const PAGE_MARGIN_X_PT = 52
export const PAGE_MARGIN_TOP_PT = 42
export const PAGE_MARGIN_BOTTOM_PT = 44

export const SAFE_AREA: Rect = {
  x: PAGE_MARGIN_X_PT / CANVAS_WIDTH_PT,
  y: PAGE_MARGIN_TOP_PT / CANVAS_HEIGHT_PT,
  w: (CANVAS_WIDTH_PT - 2 * PAGE_MARGIN_X_PT) / CANVAS_WIDTH_PT,
  h: (CANVAS_HEIGHT_PT - PAGE_MARGIN_TOP_PT - PAGE_MARGIN_BOTTOM_PT) / CANVAS_HEIGHT_PT,
}

/** 就地编辑的字段级变更；多字段块由保存队列合并，避免并发丢字 */
export type EditableBlockCommit =
  | { type: 'text'; text: string }
  /** 未带 kind 或 kind=update：改某一项文案（可为空占位） */
  | { type: 'bullets'; kind?: 'update'; index: number; text: string }
  /** 在 index 之后插入空要点 */
  | { type: 'bullets'; kind: 'insert'; index: number }
  /** 删除 index；只剩一项时清空文案、不删块 */
  | { type: 'bullets'; kind: 'remove'; index: number }
  | { type: 'kpi'; field: 'value' | 'label' | 'note'; text: string }
  | { type: 'cards'; index: number; field: 'title' | 'desc'; text: string }
  | { type: 'callout'; text: string }
  | { type: 'table'; kind: 'header'; index: number; text: string }
  | { type: 'table'; kind: 'cell'; row: number; col: number; text: string }
  | { type: 'table'; kind: 'replace'; header: string[]; rows: string[][] }
  | {
      type: 'chart'
      chart_type: ChartBlock['chart_type']
      categories: string[]
      series: ChartBlock['series']
      unit?: string | null
    }
  | { type: 'style'; style: import('@/render/blockStyle').BlockStyle | null }
