import type { BlockUpdateBody, DeckSlide } from '@/features/deck/types'
import type { EditableBlockCommit } from '@/render/types'

/** 落库前整理要点：保留空占位（刚 Enter 的新项），至少一项 */
export function sanitizeBulletsItems(items: string[]): string[] {
  return items.length > 0 ? items : ['']
}

/** 把字段级编辑叠到当前块（含尚未发出的覆盖）上，得到完整 PATCH 体 */
export function mergeBlockCommit(
  slide: DeckSlide,
  blockId: string,
  commit: EditableBlockCommit,
  previous?: BlockUpdateBody,
): BlockUpdateBody | null {
  const block = slide.blocks.find((item) => item.id === blockId)
  if (!block || block.type !== commit.type) return null

  if (commit.type === 'text' && block.type === 'text') {
    return { type: 'text', text: commit.text }
  }

  if (commit.type === 'bullets' && block.type === 'bullets') {
    // 清空的条目先保留占位，避免后续要点的 index 错位；
    // Enter 新增的空项也要留着，保存时不再整表 strip
    const base = previous?.type === 'bullets' ? previous.items : block.items
    if (commit.kind === 'insert') {
      const items = [...base]
      const at = Math.max(0, Math.min(commit.index + 1, items.length))
      items.splice(at, 0, '')
      return { type: 'bullets', items }
    }
    if (commit.kind === 'remove') {
      if (base.length <= 1) return { type: 'bullets', items: [''] }
      return {
        type: 'bullets',
        items: base.filter((_, index) => index !== commit.index),
      }
    }
    const items = base.map((item, index) => (index === commit.index ? commit.text : item))
    return { type: 'bullets', items }
  }

  if (commit.type === 'kpi' && block.type === 'kpi') {
    const base =
      previous?.type === 'kpi'
        ? previous
        : {
            type: 'kpi' as const,
            value: block.value,
            label: block.label,
            note: block.note ?? null,
          }
    return {
      type: 'kpi',
      value: commit.field === 'value' ? commit.text : base.value,
      label: commit.field === 'label' ? commit.text : base.label,
      note:
        commit.field === 'note' ? commit.text || null : (base.note ?? null),
    }
  }

  if (commit.type === 'cards' && block.type === 'cards') {
    const base = previous?.type === 'cards' ? previous.items : block.items
    return {
      type: 'cards',
      items: base.map((item, index) =>
        index === commit.index
          ? {
              title: commit.field === 'title' ? commit.text : item.title,
              desc: commit.field === 'desc' ? commit.text : item.desc,
              icon: item.icon ?? null,
            }
          : {
              title: item.title,
              desc: item.desc,
              icon: item.icon ?? null,
            },
      ),
    }
  }

  if (commit.type === 'callout' && block.type === 'callout') {
    const base =
      previous?.type === 'callout'
        ? previous
        : {
            type: 'callout' as const,
            text: block.text,
            icon: block.icon ?? null,
            variant: block.variant,
          }
    return {
      type: 'callout',
      text: commit.text,
      icon: base.icon ?? null,
      variant: base.variant,
    }
  }

  if (commit.type === 'table' && block.type === 'table') {
    if (commit.kind === 'replace') {
      return {
        type: 'table',
        header: commit.header,
        rows: commit.rows,
      }
    }

    const base =
      previous?.type === 'table'
        ? { header: previous.header, rows: previous.rows }
        : { header: block.header, rows: block.rows }

    if (commit.kind === 'header') {
      return {
        type: 'table',
        header: base.header.map((cell, index) =>
          index === commit.index ? commit.text : cell,
        ),
        rows: base.rows,
      }
    }

    return {
      type: 'table',
      header: base.header,
      rows: base.rows.map((row, rowIndex) =>
        rowIndex === commit.row
          ? row.map((cell, colIndex) =>
              colIndex === commit.col ? commit.text : cell,
            )
          : row,
      ),
    }
  }

  if (commit.type === 'chart' && block.type === 'chart') {
    return {
      type: 'chart',
      chart_type: commit.chart_type,
      categories: commit.categories,
      series: commit.series,
      unit: commit.unit ?? null,
    }
  }

  return null
}
