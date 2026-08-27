/**
 * 前后端 grow 归一化对齐检查：shared/flex-fixtures/normalize-grow-cases.json
 * 的期望值由后端 normalize(clamp_title_grow=False) 生成，两端任一改动都会红。
 * 运行：cd frontend && npx --yes tsx --tsconfig tsconfig.app.json scripts/flex-normalize-parity.mts
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { normalizeGrows } from '../src/features/deck/flexNormalize.ts'
import type { FlexContainer, FlexNode } from '../src/render/flexLayout.ts'

type Case = {
  name: string
  tree: FlexContainer
  expected_grows: Record<string, number>
}

const here = dirname(fileURLToPath(import.meta.url))
const fixture = resolve(here, '../../shared/flex-fixtures/normalize-grow-cases.json')
const { cases } = JSON.parse(readFileSync(fixture, 'utf8')) as { cases: Case[] }

assert.ok(cases.length > 0, '没有读到归一化用例')

function collectGrows(node: FlexNode, out: Record<string, number> = {}) {
  out[node.id] = node.grow ?? 1
  if (node.type !== 'block') {
    for (const child of node.children) collectGrows(child, out)
  }
  return out
}

for (const item of cases) {
  const once = normalizeGrows(item.tree)
  assert.deepEqual(
    collectGrows(once),
    item.expected_grows,
    `${item.name}：与后端 normalize 结果不一致`,
  )

  const twice = normalizeGrows(once)
  assert.deepEqual(collectGrows(twice), collectGrows(once), `${item.name}：归一化不幂等`)
  console.log(`grow 归一对齐 OK：${item.name}`)
}
