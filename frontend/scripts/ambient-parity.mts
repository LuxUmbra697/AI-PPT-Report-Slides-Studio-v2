/**
 * 前后端主题氛围层对齐检查：shared/ambient-fixtures/theme-cases.json
 * 的期望值由 backend/scripts/dump_ambient_fixture.py 生成，两端任一改动都会红。
 * 运行：cd frontend && npx --yes tsx --tsconfig tsconfig.app.json scripts/ambient-parity.mts
 */
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
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
    rotation: shape.rotation ?? 0,
  }
}

function loadTheme(themeId: string): Theme {
  const directPath = resolve(sharedDir, `themes/${themeId}.json`)
  if (existsSync(directPath)) {
    return JSON.parse(readFileSync(directPath, 'utf8')) as Theme
  }

  const catalog = JSON.parse(
    readFileSync(resolve(sharedDir, 'themes/catalog.json'), 'utf8'),
  ) as {
    presets?: Array<{
      id: string
      base: string
      category?: string
      name: string
      description: string
      palette?: Partial<Theme['palette']>
      shape?: Partial<Theme['shape']>
      ambient?: Theme['ambient']
    }>
  }
  const visuals = JSON.parse(
    readFileSync(resolve(sharedDir, 'themes/visuals.json'), 'utf8'),
  ) as {
    preset_families?: Record<string, string>
    category_families?: Record<string, string>
    families?: Record<
      string,
      {
        cover_variant?: NonNullable<Theme['visual']>['cover_variant']
        content_variant?: NonNullable<Theme['visual']>['content_variant']
        transition?: NonNullable<Theme['visual']>['transition']
        ambient?: Theme['ambient']
      }
    >
  }
  const preset = catalog.presets?.find((item) => item.id === themeId)
  assert.ok(preset, `主题目录中找不到 ${themeId}`)
  const base = loadTheme(preset.base)
  const familyId =
    visuals.preset_families?.[themeId] ??
    visuals.category_families?.[preset.category ?? ''] ??
    'classic'
  const family = visuals.families?.[familyId]
  return {
    ...structuredClone(base),
    id: preset.id,
    name: preset.name,
    description: preset.description,
    palette: { ...base.palette, ...preset.palette },
    shape: { ...base.shape, ...preset.shape },
    ambient: [...(preset.ambient ?? base.ambient ?? []), ...(family?.ambient ?? [])],
    visual: {
      family: familyId,
      cover_variant: family?.cover_variant ?? 'editorial',
      content_variant: family?.content_variant ?? 'clean',
      transition: family?.transition ?? 'fade',
    },
  }
}

function roundNumbers(value: unknown): unknown {
  if (typeof value === 'number') return Math.round(value * 1e12) / 1e12
  if (Array.isArray(value)) return value.map(roundNumbers)
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, item]) => [
        key,
        roundNumbers(item),
      ]),
    )
  }
  return value
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
  assert.deepEqual(
    roundNumbers(actual),
    roundNumbers(item.expected_shapes),
    `${label}：与后端 iter_ambient_shapes 结果不一致`,
  )
  console.log(`氛围层对齐 OK：${label}（${actual.length} 个图元）`)
}
