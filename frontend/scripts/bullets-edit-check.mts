/**
 * 列表增删要点：merge / sanitize 自检
 * 运行：cd frontend && npx --yes tsx --tsconfig tsconfig.app.json scripts/bullets-edit-check.mts
 */
import assert from 'node:assert/strict'
import {
  mergeBlockCommit,
  sanitizeBulletsItems,
} from '../src/features/deck/mergeBlockCommit.ts'
import type { DeckSlide } from '../src/features/deck/types.ts'

function slideWithBullets(items: string[]): DeckSlide {
  return {
    id: 's1',
    outline_page_id: 'p1',
    position: 1,
    layout_id: 'bullets',
    layout_mode: 'flex',
    layout_tree: null,
    title: 't',
    status: 'ready',
    error: null,
    revision: 1,
    issues: [],
    blocks: [
      {
        id: 'b1',
        slot_id: 'b1',
        type: 'bullets',
        items,
        locked: false,
      },
    ],
  } as DeckSlide
}

{
  const body = mergeBlockCommit(slideWithBullets(['要点']), 'b1', {
    type: 'bullets',
    index: 0,
    text: '第一项',
  })
  assert.deepEqual(body, { type: 'bullets', items: ['第一项'] })
  console.log('update OK')
}

{
  const body = mergeBlockCommit(slideWithBullets(['第一项']), 'b1', {
    type: 'bullets',
    kind: 'insert',
    index: 0,
  })
  assert.deepEqual(body, { type: 'bullets', items: ['第一项', ''] })
  console.log('insert after index OK')
}

{
  const body = mergeBlockCommit(
    slideWithBullets(['第一项', '']),
    'b1',
    { type: 'bullets', kind: 'insert', index: 1 },
    { type: 'bullets', items: ['第一项', '第二'] },
  )
  assert.deepEqual(body, { type: 'bullets', items: ['第一项', '第二', ''] })
  console.log('insert with previous override OK')
}

{
  const body = mergeBlockCommit(slideWithBullets(['a', 'b', 'c']), 'b1', {
    type: 'bullets',
    kind: 'remove',
    index: 1,
  })
  assert.deepEqual(body, { type: 'bullets', items: ['a', 'c'] })
  console.log('remove OK')
}

{
  const body = mergeBlockCommit(slideWithBullets(['仅一项']), 'b1', {
    type: 'bullets',
    kind: 'remove',
    index: 0,
  })
  assert.deepEqual(body, { type: 'bullets', items: [''] })
  console.log('remove last keeps placeholder OK')
}

{
  assert.deepEqual(sanitizeBulletsItems(['要点', '']), ['要点', ''])
  assert.deepEqual(sanitizeBulletsItems([]), [''])
  assert.deepEqual(sanitizeBulletsItems(['a', 'b']), ['a', 'b'])
  console.log('sanitize keeps empty placeholder OK')
}

console.log('\nbullets edit check 全部通过')
