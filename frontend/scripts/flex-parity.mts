/**
 * 前后端 flex solver 对齐检查：遍历 shared/flex-presets/golden-*.json。
 * 运行：cd frontend && npx --yes tsx scripts/flex-parity.mts
 */
import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { solve, type FlexContainer } from '../src/render/flexLayout.ts'

type Golden = {
  tree: FlexContainer
  expected_rects: Record<string, { x: number; y: number; w: number; h: number }>
}

const here = dirname(fileURLToPath(import.meta.url))
const presetsDir = resolve(here, '../../shared/flex-presets')
const files = readdirSync(presetsDir)
  .filter((name) => name.startsWith('golden') && name.endsWith('.json'))
  .sort()

assert.ok(files.length > 0, 'no golden fixtures found')

for (const file of files) {
  const golden = JSON.parse(readFileSync(resolve(presetsDir, file), 'utf8')) as Golden
  const placed = Object.fromEntries(solve(golden.tree).map((p) => [p.block_id, p.rect]))

  for (const [blockId, expected] of Object.entries(golden.expected_rects)) {
    const actual = placed[blockId]
    assert.ok(actual, `${file}: missing rect for ${blockId}`)
    assert.equal(actual.x, expected.x, `${file}: ${blockId}.x`)
    assert.equal(actual.y, expected.y, `${file}: ${blockId}.y`)
    assert.equal(actual.w, expected.w, `${file}: ${blockId}.w`)
    assert.equal(actual.h, expected.h, `${file}: ${blockId}.h`)
  }
  console.log(`flex parity OK: ${file} (${Object.keys(golden.expected_rects).join(', ')})`)
}
