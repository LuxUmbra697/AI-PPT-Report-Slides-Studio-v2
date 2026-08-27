/**
 * 前后端主题氛围层对齐检查：shared/ambient-fixtures/theme-cases.json
 * 的期望值由 backend/scripts/dump_ambient_fixture.py 生成，两端任一改动都会红。
 * 运行：cd frontend && npx --yes tsx --tsconfig tsconfig.app.json scripts/ambient-parity.mts
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { iterAmbientShapes, type AmbientShape } from '../src/render/ambient.ts'
import type { Rect, Theme } from '../src/render/types.ts'

type Case = {
  theme_id: string
  layout_id: string
  slide_index: number
  occupied_id: string
  occupied: Rect[]
  expected_shapes: Record<string, unknown>[]
}

const here = dirname(fileURLToPath(import.meta.url))
const sharedDir = resolve(here, '../../shared')
const { cases } = JSON.parse(
  readFileSync(resolve(sharedDir, 'ambient-fixtures/theme-cases.json'), 'utf8'),
) as { cases: Case[] }

assert.ok(cases.length > 0, '没有读到氛围层用例')

/** 后端 model_dump 会补齐所有默认值，前端补上同一套默认再比 */
function normalize(shape: AmbientShape) {
  return {
    kind: shape.kind,
    rect: shape.rect,
    color: shape.color,
    text: shape.text ?? null,
    font: shape.font ?? null,
    size_pt: shape.size_pt ?? null,
    weight: shape.weight ?? null,
    letter_spacing_pt: shape.letter_spacing_pt ?? 0,
    align: shape.align ?? 'left',
  }
}

function loadTheme(themeId: string): Theme {
  return JSON.parse(readFileSync(resolve(sharedDir, `themes/${themeId}.json`), 'utf8')) as Theme
}

for (const item of cases) {
  const theme = loadTheme(item.theme_id)
  const actual = iterAmbientShapes(
    theme,
    item.layout_id,
    item.slide_index,
    item.occupied,
  ).map(normalize)
  const label = `${item.theme_id}/${item.layout_id}/${item.occupied_id}`
  assert.deepEqual(actual, item.expected_shapes, `${label}：与后端 iter_ambient_shapes 结果不一致`)
  console.log(`氛围层对齐 OK：${label}（${actual.length} 个图元）`)
}
