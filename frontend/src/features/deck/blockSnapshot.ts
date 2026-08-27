import type { BlockUpdateBody, DeckSlide } from '@/features/deck/types'
import type { BlockStyle } from '@/render/blockStyle'

type Block = DeckSlide['blocks'][number]

/** 抽出块的可写内容，供撤销栈 before/after 对比 */
export function contentBodyFromBlock(block: Block): BlockUpdateBody | null {
  switch (block.type) {
    case 'text':
      return { type: 'text', text: block.text }
    case 'bullets':
      return { type: 'bullets', items: [...block.items] }
    case 'kpi':
      return {
        type: 'kpi',
        value: block.value,
        label: block.label,
        note: block.note ?? null,
      }
    case 'cards':
      return {
        type: 'cards',
        items: block.items.map((item) => ({
          title: item.title,
          desc: item.desc,
          icon: item.icon ?? null,
        })),
      }
    case 'callout':
      return {
        type: 'callout',
        text: block.text,
        icon: block.icon ?? null,
        variant: block.variant,
      }
    case 'table':
      return {
        type: 'table',
        header: [...block.header],
        rows: block.rows.map((row) => [...row]),
      }
    case 'chart':
      return {
        type: 'chart',
        chart_type: block.chart_type,
        categories: [...block.categories],
        series: block.series.map((item) => ({
          name: item.name,
          values: [...item.values],
        })),
        unit: block.unit ?? null,
      }
    default:
      return null
  }
}

export function styleFromBlock(block: Block): BlockStyle | null {
  return block.style ?? null
}

export function applyContentBody(block: Block, body: BlockUpdateBody): Block {
  if (body.type !== block.type) return block
  if (body.type === 'text' && block.type === 'text') {
    return { ...block, text: body.text }
  }
  if (body.type === 'bullets' && block.type === 'bullets') {
    return { ...block, items: body.items }
  }
  if (body.type === 'kpi' && block.type === 'kpi') {
    return {
      ...block,
      value: body.value,
      label: body.label,
      note: body.note ?? null,
    }
  }
  if (body.type === 'cards' && block.type === 'cards') {
    return { ...block, items: body.items }
  }
  if (body.type === 'callout' && block.type === 'callout') {
    return {
      ...block,
      text: body.text,
      icon: body.icon ?? null,
      variant: body.variant,
    }
  }
  if (body.type === 'table' && block.type === 'table') {
    return { ...block, header: body.header, rows: body.rows }
  }
  if (body.type === 'chart' && block.type === 'chart') {
    return {
      ...block,
      chart_type: body.chart_type,
      categories: body.categories,
      series: body.series,
      unit: body.unit ?? null,
    }
  }
  return block
}

export function sameContent(a: BlockUpdateBody, b: BlockUpdateBody): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

export function sameStyle(a: BlockStyle | null, b: BlockStyle | null): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}
