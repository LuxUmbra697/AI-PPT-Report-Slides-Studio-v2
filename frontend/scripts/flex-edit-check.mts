/**
 * 编辑交互自检：行内单元格高度互不联动、八向手柄都能取到分隔线、像素级微调。
 * 运行：cd frontend && npx --yes tsx --tsconfig tsconfig.app.json scripts/flex-edit-check.mts
 * （需要 tsconfig.app.json 才能解析 @/ 别名）
 */
import assert from 'node:assert/strict'
import {
  edgeCornerInset,
  gripOffsetStyle,
  resolveCornerAxisLock,
} from '../src/features/deck/flexEditGeometry.ts'
import { normalizeGrows } from '../src/features/deck/flexNormalize.ts'
import {
  GROW_MIN,
  SPACER_SEED_RATIO,
  applyVerticalResizeDrag,
  ensureResizePair,
  findContainerById,
  growsFromDividerDrag,
  leafOffset,
  resolveDropTarget,
  ratiosFromDividerDrag,
  setLeafOffset,
  snapRatios,
  updateChildGrows,
  type ResizeSide,
} from '../src/features/deck/flexTree.ts'
import { solve, type FlexContainer } from '../src/render/flexLayout.ts'

const CANVAS_W_PT = 960
const CANVAS_H_PT = 540

const heights = (tree: FlexContainer) =>
  Object.fromEntries(solve(tree).map((p) => [p.block_id, Number((p.rect.h * 540).toFixed(1))]))

/** 根列 → 行 → 两个叶子，对应「左右并排」的版面 */
function twoColumnTree(): FlexContainer {
  return {
    type: 'column',
    id: 'root',
    gap_pt: 16,
    children: [
      { type: 'block', id: 'leaf-title', block_id: 'title', grow: 0.5, text_style: 'title' },
      {
        type: 'row',
        id: 'row',
        gap_pt: 16,
        ratios: [50, 50],
        grow: 1.5,
        children: [
          { type: 'block', id: 'leaf-left', block_id: 'left', grow: 1 },
          { type: 'block', id: 'leaf-right', block_id: 'right', grow: 1 },
        ],
      },
    ],
  }
}

// 问题 2：拉左侧单元格高度，右侧不该跟着变
{
  const before = heights(twoColumnTree())
  const pair = ensureResizePair(twoColumnTree(), 'left', 'y', 'after')
  assert.ok(pair, '左侧单元格应能取到纵向分隔线')

  const column = pair.tree
  const grows = growsFromDividerDrag({ grows: [4, 0.25], topIndex: 0, t: 0.5 })
  const dragged = updateChildGrows(column, pair.containerId, grows)
  assert.ok(dragged, '纵向拖拽应产出新树')

  const after = heights(dragged)
  assert.ok(after.left < before.left, `左侧应变矮：${before.left} -> ${after.left}`)
  assert.equal(after.right, before.right, `右侧不应变化：${before.right} -> ${after.right}`)
  assert.equal(after.title, before.title, '标题不应受影响')
  console.log(`问题2 OK：左 ${before.left}→${after.left}pt，右保持 ${after.right}pt`)
}

// ensure 高度后再 ensure 宽度：应绑外层 row，不包内层 seed row；纯纵向拖宽度不变
{
  const origin = Object.fromEntries(solve(twoColumnTree()).map((p) => [p.block_id, p.rect]))
  const yPair = ensureResizePair(twoColumnTree(), 'left', 'y', 'after')!
  const xPair = ensureResizePair(yPair.tree, 'left', 'x', 'after')!
  assert.equal(
    xPair.containerId,
    'row',
    `高度 cell 后宽度应对外层 row，实际 container=${xPair.containerId}`,
  )
  const afterY = Object.fromEntries(solve(yPair.tree).map((p) => [p.block_id, p.rect]))
  assert.ok(
    Math.abs(afterY.left!.w - origin.left!.w) * CANVAS_W_PT < 0.5,
    `纯 ensureY 不应改宽度，dw=${((afterY.left!.w - origin.left!.w) * CANVAS_W_PT).toFixed(2)}`,
  )
  const col = findContainerById(yPair.tree, yPair.containerId)!
  const grows = col.children.map((c) => c.grow ?? 1)
  const total = grows.reduce((a, b) => a + b, 0)
  const startT = grows.slice(0, yPair.index + 1).reduce((a, b) => a + b, 0) / total
  const left = afterY.left!
  const dragged = applyVerticalResizeDrag({
    root: yPair.tree,
    columnId: yPair.containerId,
    topIndex: yPair.index,
    colH: left.h,
    startT,
    originY: left.y + left.h,
    pointerY: left.y + left.h - 0.08,
  })!
  const afterDrag = Object.fromEntries(solve(dragged).map((p) => [p.block_id, p.rect]))
  assert.ok(
    Math.abs(afterDrag.left!.w - origin.left!.w) * CANVAS_W_PT < 0.5,
    `纵向拖后宽度应不变，dw=${((afterDrag.left!.w - origin.left!.w) * CANVAS_W_PT).toFixed(2)}`,
  )
  console.log('纵拉不改宽 OK：ensureY→X 绑外层 row，grow 拖 dw=0')
}

/** 三列 KPI 行（窄块） */
function threeKpiTree(): FlexContainer {
  return {
    type: 'column',
    id: 'root',
    gap_pt: 14,
    children: [
      { type: 'block', id: 'leaf-title', block_id: 'title', grow: 0.45, text_style: 'title' },
      {
        type: 'row',
        id: 'kpi-row',
        gap_pt: 12,
        ratios: [33, 33, 34],
        grow: 0.9,
        children: [
          { type: 'block', id: 'leaf-kpi-1', block_id: 'kpi_1', grow: 1 },
          { type: 'block', id: 'leaf-kpi-2', block_id: 'kpi_2', grow: 1 },
          { type: 'block', id: 'leaf-kpi-3', block_id: 'kpi_3', grow: 1 },
        ],
      },
    ],
  }
}

// 纵拉前拆掉左右 spacer 宽度种子包装，避免窄 KPI 被挤扁
{
  const polluted: FlexContainer = {
    type: 'column',
    id: 'root',
    gap_pt: 14,
    children: [
      {
        type: 'row',
        id: 'content-row',
        gap_pt: 16,
        ratios: [50, 50],
        grow: 1.5,
        children: [
          { type: 'block', id: 'leaf-steps', block_id: 'steps', grow: 1 },
          {
            type: 'row',
            id: 'width-wrap',
            gap_pt: 0,
            grow: 1,
            ratios: [0, 100, 0],
            children: [
              { type: 'column', id: 'spacer-l', children: [], gap_pt: 0, grow: 1 },
              { type: 'block', id: 'leaf-kpi', block_id: 'kpi', grow: 4 },
              { type: 'column', id: 'spacer-r', children: [], gap_pt: 0, grow: 1 },
            ],
          },
        ],
      },
    ],
  }
  const before = solve(polluted).find((p) => p.block_id === 'kpi')!.rect
  const pair = ensureResizePair(polluted, 'kpi', 'y', 'after')!
  const afterEnsure = solve(pair.tree).find((p) => p.block_id === 'kpi')!.rect
  assert.ok(
    afterEnsure.w + 1e-6 >= before.w,
    `拆包装后宽度不应变窄：${before.w} → ${afterEnsure.w}`,
  )
  // 包装应被拆掉：kpi 父级不再是带双 spacer 的 row
  const parent = findContainerById(pair.tree, pair.containerId)!
  assert.equal(parent.type, 'column', '纵拉 ensure 后应落在 column 分隔上')
  assert.ok(
    !JSON.stringify(pair.tree).includes('"id":"width-wrap"'),
    '宽度种子 row 应被 unwrap 掉',
  )
  console.log(
    `拆宽度种子 OK：kpi w ${((before.w) * CANVAS_W_PT).toFixed(1)}→${(afterEnsure.w * CANVAS_W_PT).toFixed(1)}pt`,
  )
}

// 窄 KPI：ensureY + 纵拖不改宽；相对 inset 上下边可点；角点小横向锁 Y
{
  const origin = Object.fromEntries(solve(threeKpiTree()).map((p) => [p.block_id, p.rect]))
  const yPair = ensureResizePair(threeKpiTree(), 'kpi_1', 'y', 'after')!
  const afterY = Object.fromEntries(solve(yPair.tree).map((p) => [p.block_id, p.rect]))
  assert.ok(
    Math.abs(afterY.kpi_1!.w - origin.kpi_1!.w) * CANVAS_W_PT < 0.5,
    `KPI ensureY 不应改宽，dw=${((afterY.kpi_1!.w - origin.kpi_1!.w) * CANVAS_W_PT).toFixed(2)}`,
  )
  const inset = edgeCornerInset(afterY.kpi_1!)
  const edgeW = afterY.kpi_1!.w - 2 * inset.x
  assert.ok(edgeW > 0.02, `窄 KPI 上下边命中宽度应 >0.02，实际 ${edgeW.toFixed(3)}`)
  assert.equal(resolveCornerAxisLock(4, 20), 'y', '横向 <8px 应锁 Y')
  assert.equal(resolveCornerAxisLock(12, 20), 'y', '纵向主导应锁 Y')
  assert.notEqual(resolveCornerAxisLock(20, 4), 'y', '明显横向不应锁死 Y')

  const col = findContainerById(yPair.tree, yPair.containerId)!
  const grows = col.children.map((c) => c.grow ?? 1)
  const total = grows.reduce((a, b) => a + b, 0)
  const startT = grows.slice(0, yPair.index + 1).reduce((a, b) => a + b, 0) / total
  const kpi = afterY.kpi_1!
  const dragged = applyVerticalResizeDrag({
    root: yPair.tree,
    columnId: yPair.containerId,
    topIndex: yPair.index,
    colH: kpi.h,
    startT,
    originY: kpi.y + kpi.h,
    pointerY: kpi.y + kpi.h - 0.06,
  })!
  const afterDrag = Object.fromEntries(solve(dragged).map((p) => [p.block_id, p.rect]))
  assert.ok(
    Math.abs(afterDrag.kpi_1!.w - origin.kpi_1!.w) * CANVAS_W_PT < 0.5,
    `KPI 纵拖后宽度应不变，dw=${((afterDrag.kpi_1!.w - origin.kpi_1!.w) * CANVAS_W_PT).toFixed(2)}`,
  )
  // 角点主轴为 Y：不 ensureX，树宽保持
  assert.equal(
    ensureResizePair(yPair.tree, 'kpi_1', 'x', 'after')!.containerId,
    'kpi-row',
    '若补 ensureX 应绑 kpi-row（验证宽度对正确）；纯 Y 路径不应调用）',
  )
  const grip = gripOffsetStyle(kpi)
  assert.ok(
    String(grip.left).includes('- 22px'),
    `窄 KPI 排序柄应在块左侧外，实际 left=${grip.left}`,
  )
  const edgeGrip = gripOffsetStyle({ x: 0.01, y: 0.2, w: 0.2, h: 0.3 })
  assert.ok(
    String(edgeGrip.top).includes('- 22px'),
    `贴左边时排序柄应改放到上方，实际 top=${edgeGrip.top}`,
  )
  console.log(
    `窄 KPI 纵拉 OK：edgeW=${edgeW.toFixed(3)}，dw=0，角点 dx<8 → Y，柄在块外`,
  )
}

// 问题 5a：八个方向的手柄都能取到一条可拖的分隔线
{
  const cases: [('x' | 'y'), ResizeSide][] = [
    ['y', 'before'],
    ['y', 'after'],
    ['x', 'before'],
    ['x', 'after'],
  ]
  for (const blockId of ['title', 'left', 'right']) {
    for (const [axis, side] of cases) {
      const pair = ensureResizePair(twoColumnTree(), blockId, axis, side)
      assert.ok(pair, `${blockId} 的 ${axis}/${side} 手柄取不到分隔线`)
      const container = solve(pair.tree)
      assert.equal(container.length, 3, `${blockId} ${axis}/${side} 后内容块数量变了`)
      const maxBottom = Math.max(...container.map((p) => p.rect.y + p.rect.h))
      const maxRight = Math.max(...container.map((p) => p.rect.x + p.rect.w))
      assert.ok(maxBottom <= 1.0001, `${blockId} ${axis}/${side} 越界 bottom=${maxBottom}`)
      assert.ok(maxRight <= 1.0001, `${blockId} ${axis}/${side} 越界 right=${maxRight}`)
    }
  }
  console.log('问题5a OK：3 个块 × 4 个方向手柄都能拖，且不越界')
}

// 问题 5b：像素级微调，越界被钳制
{
  // left 块底边本就贴着画布下沿，所以纵向取向上微调
  const nudged = setLeafOffset(twoColumnTree(), 'left', 12, -8)
  assert.ok(nudged)
  assert.deepEqual(leafOffset(nudged, 'left'), { x: 12, y: -8 })

  const base = Object.fromEntries(solve(twoColumnTree()).map((p) => [p.block_id, p.rect]))
  const moved = Object.fromEntries(solve(nudged).map((p) => [p.block_id, p.rect]))
  assert.equal(Number(((moved.left.x - base.left.x) * 960).toFixed(1)), 12)
  assert.equal(Number(((moved.left.y - base.left.y) * 540).toFixed(1)), -8)
  assert.equal(moved.left.w, base.left.w, '微调不应改变尺寸')
  assert.equal(moved.left.h, base.left.h, '微调不应改变尺寸')
  assert.deepEqual(moved.right, base.right, '微调不应影响兄弟')

  for (const [dx, dy] of [
    [9999, 9999],
    [-9999, -9999],
  ]) {
    const far = setLeafOffset(twoColumnTree(), 'left', dx!, dy!)!
    for (const placed of solve(far)) {
      assert.ok(
        placed.rect.x >= 0 &&
          placed.rect.y >= 0 &&
          placed.rect.x + placed.rect.w <= 1.0001 &&
          placed.rect.y + placed.rect.h <= 1.0001,
        `偏移 ${dx}/${dy} 未被钳制：${JSON.stringify(placed.rect)}`,
      )
    }
  }
  console.log('问题5b OK：偏移 12/-8pt 精确生效且不影响兄弟，越界被钳制在画布内')
}

// 问题 4：双列比例只在靠近设计值时吸附
{
  assert.deepEqual(snapRatios([40, 60]), [38, 62], '靠近 38 应吸附')
  assert.deepEqual(snapRatios([55, 45]), [55, 45], '55/45 应原样保留')
  assert.deepEqual(snapRatios([72, 28]), [72, 28], '72/28 应原样保留')
  console.log('问题4 OK：40/60→38/62 吸附，55/45 与 72/28 保留精确值')
}

// 左侧缩放 ensure：缺邻侧只种种子 spacer，几乎不跳；且可拖回通栏原位
{
  const single: FlexContainer = {
    type: 'column',
    id: 'root',
    gap_pt: 16,
    children: [{ type: 'block', id: 'leaf-a', block_id: 'a', grow: 1 }],
  }
  const origin = solve(single).find((p) => p.block_id === 'a')!.rect
  const pair = ensureResizePair(single, 'a', 'x', 'before')
  assert.ok(pair, '单块左侧应能 ensure 出横向分隔')
  const row = pair.tree.children.find((c) => c.type === 'row')
  assert.ok(row && row.type === 'row' && row.ratios, '应包成 row')
  assert.equal(row.ratios!.length, 2)
  assert.ok(
    Math.abs(row.ratios![0]! - SPACER_SEED_RATIO) < 0.05,
    `左侧 spacer 应为 ~${SPACER_SEED_RATIO}，实际 ${row.ratios}`,
  )
  const afterEnsure = solve(pair.tree).find((p) => p.block_id === 'a')!.rect
  assert.ok(
    Math.abs(afterEnsure.x - origin.x) * 960 < 1,
    `ensure 后左缘跳变应 <1pt，实际 ${(Math.abs(afterEnsure.x - origin.x) * 960).toFixed(2)}pt`,
  )

  const restored = ratiosFromDividerDrag({
    ratios: [...row.ratios!],
    leftIndex: 0,
    t: 0,
    minLeft: 0,
    minRight: 0.05,
  })
  const restoredTree = structuredClone(pair.tree) as FlexContainer
  const restoredRow = restoredTree.children.find((c) => c.type === 'row') as FlexContainer
  restoredRow.ratios = restored
  const back = solve(restoredTree).find((p) => p.block_id === 'a')!.rect
  assert.ok(
    Math.abs(back.x - origin.x) * 960 < 0.5,
    `拖回 t=0 应恢复原位，gap=${((back.x - origin.x) * 960).toFixed(2)}pt`,
  )
  console.log(
    `左侧 ensure OK：seed=${row.ratios!.map((r) => r.toFixed(2)).join('/')}，可拖回原位`,
  )
}

// 空白落点：指针落在块外间隙仍能解析 DropTarget
{
  const tree = twoColumnTree()
  const placements = new Map(solve(tree).map((p) => [p.block_id, p.rect]))
  const left = placements.get('left')!
  const pointer = {
    x: left.x + left.w + 0.01,
    y: left.y + left.h / 2,
  }
  const drop = resolveDropTarget({ root: tree, placements, pointer })
  assert.ok(drop, '块间隙应能命中落点')
  console.log(`空白落点 OK：parent=${drop.parentId} index=${drop.index}`)
}

// 下半区命中：index=下一块，线贴下一块顶边（前缘）而非当前块底边
{
  const tree: FlexContainer = {
    type: 'column',
    id: 'root',
    gap_pt: 16,
    children: [
      { type: 'block', id: 'leaf-a', block_id: 'a', grow: 1 },
      { type: 'block', id: 'leaf-b', block_id: 'b', grow: 1 },
    ],
  }
  const placements = new Map(solve(tree).map((p) => [p.block_id, p.rect]))
  const a = placements.get('a')!
  const b = placements.get('b')!
  const drop = resolveDropTarget({
    root: tree,
    placements,
    pointer: { x: a.x + a.w / 2, y: a.y + a.h * 0.75 },
  })
  assert.ok(drop, '下半区应有落点')
  assert.equal(drop.index, 1)
  assert.ok(
    Math.abs(drop.line.y - b.y) < 1e-6,
    `线应贴 b 顶边：line.y=${drop.line.y} b.y=${b.y}`,
  )
  assert.ok(
    Math.abs(drop.line.y - (a.y + a.h)) > 1e-4,
    '线不应贴在 a 底边（中间有 gap）',
  )
  console.log('落点前缘 OK：下半区线贴下一块上边界')
}

// wrap cell [body, spacer] + footer：body 下半区应上收到 footer 顶边，而非 spacer 顶（body 下沿）
{
  const tree: FlexContainer = {
    type: 'column',
    id: 'root',
    gap_pt: 16,
    children: [
      { type: 'block', id: 'leaf-t', block_id: 'title', grow: 0.5 },
      {
        type: 'column',
        id: 'cell-body',
        gap_pt: 0,
        grow: 1.5,
        children: [
          { type: 'block', id: 'leaf-b', block_id: 'body', grow: 4 },
          {
            type: 'column',
            id: 'spacer-tail',
            children: [],
            gap_pt: 0,
            grow: 0.001,
          },
        ],
      },
      { type: 'block', id: 'leaf-f', block_id: 'footer', grow: 0.5 },
    ],
  }
  const placements = new Map(solve(tree).map((p) => [p.block_id, p.rect]))
  const body = placements.get('body')!
  const footer = placements.get('footer')!
  const drop = resolveDropTarget({
    root: tree,
    placements,
    pointer: { x: body.x + body.w / 2, y: body.y + body.h * 0.8 },
  })
  assert.ok(drop, 'wrap cell 下半区应有落点')
  assert.equal(drop.parentId, 'root')
  assert.equal(drop.index, 2, `应插到 footer 前，实际 index=${drop.index}`)
  assert.ok(
    Math.abs(drop.line.y - footer.y) < 1e-6,
    `线应贴 footer 顶边，line.y=${drop.line.y} footer.y=${footer.y}`,
  )
  assert.ok(
    Math.abs(drop.line.y - (body.y + body.h)) > 1e-4,
    '线不应贴在 body 下沿（spacer 顶）',
  )
  console.log('落点前缘 OK：wrap cell 下半区上收到下一块内容顶边')
}

// 末块下半区（reorder）：勿贴底边（易切字）；改为插到该块前，线贴上边界
{
  const tree: FlexContainer = {
    type: 'column',
    id: 'root',
    gap_pt: 16,
    children: [
      { type: 'block', id: 'leaf-t', block_id: 'title', grow: 0.5 },
      { type: 'block', id: 'leaf-b', block_id: 'body', grow: 1.5 },
    ],
  }
  const placements = new Map(solve(tree).map((p) => [p.block_id, p.rect]))
  const body = placements.get('body')!
  const drop = resolveDropTarget({
    root: tree,
    placements,
    pointer: { x: body.x + body.w / 2, y: body.y + body.h * 0.85 },
  })
  assert.ok(drop, '末块下半区应有落点')
  assert.equal(drop.index, 1, `应插到 body 前，实际 index=${drop.index}`)
  assert.ok(
    Math.abs(drop.line.y - body.y) < 1e-6,
    `线应贴 body 顶边，line.y=${drop.line.y} body.y=${body.y}`,
  )
  assert.ok(
    Math.abs(drop.line.y - (body.y + body.h)) > 1e-4,
    '线不应贴在 body 底边',
  )
  console.log('落点前缘 OK：末块下半区线贴其上边界')

  // insert 同一位置要能落到块后：空白就是用户想放新块的地方
  const inserted = resolveDropTarget({
    root: tree,
    placements,
    pointer: { x: body.x + body.w / 2, y: body.y + body.h * 0.85 },
    mode: 'insert',
  })
  assert.ok(inserted, '末块下半区 insert 应有落点')
  assert.equal(inserted.index, 2, `insert 应落到 body 后，实际 index=${inserted.index}`)
  console.log('插入落点 OK：末块下方可插到其后')
}

// 标题旁高图留下的整片空白：insert 落进 spacer 本身，reorder 仍上收到父级
{
  const tree: FlexContainer = {
    type: 'row',
    id: 'root',
    gap_pt: 16,
    ratios: [55, 45],
    children: [
      {
        type: 'column',
        id: 'text-col',
        gap_pt: 16,
        grow: 1,
        children: [
          { type: 'block', id: 'leaf-title', block_id: 'title', grow: 0.6, text_style: 'title' },
          { type: 'column', id: 'spacer-tail', children: [], gap_pt: 0, grow: 1.4 },
        ],
      },
      { type: 'block', id: 'leaf-image', block_id: 'image', grow: 1 },
    ],
  }
  const placements = new Map(solve(tree).map((p) => [p.block_id, p.rect]))
  const title = placements.get('title')!
  // 标题正下方的空白中段
  const pointer = { x: title.x + title.w / 2, y: title.y + title.h + 0.06 }

  const inserted = resolveDropTarget({ root: tree, placements, pointer, mode: 'insert' })
  assert.ok(inserted, '空白区 insert 应有落点')
  assert.equal(
    inserted.parentId,
    'spacer-tail',
    `insert 应落进空白占位，实际 parent=${inserted.parentId}`,
  )
  assert.equal(inserted.index, 0)

  const reordered = resolveDropTarget({ root: tree, placements, pointer })
  assert.ok(reordered, '空白区 reorder 应有落点')
  assert.notEqual(reordered.parentId, 'spacer-tail', 'reorder 不应把块搬进空白占位')
  console.log(
    `插入落点 OK：空白 insert→${inserted.parentId}，reorder→${reordered.parentId}`,
  )
}

// 上下缩放：缺侧 wrap gap=0，ensure 几乎不跳，可拖回满高
{
  const single: FlexContainer = {
    type: 'column',
    id: 'root',
    gap_pt: 16,
    children: [{ type: 'block', id: 'leaf-a', block_id: 'a', grow: 1 }],
  }
  const origin = solve(single).find((p) => p.block_id === 'a')!.rect

  for (const side of ['before', 'after'] as const) {
    const pair = ensureResizePair(single, 'a', 'y', side)
    assert.ok(pair, `单块 ${side} 应能 ensure 出纵向分隔`)
    const afterEnsure = solve(pair.tree).find((p) => p.block_id === 'a')!.rect
    assert.ok(
      Math.abs(afterEnsure.y - origin.y) * CANVAS_H_PT < 1,
      `${side} ensure 后顶边跳变应 <1pt，实际 ${((afterEnsure.y - origin.y) * CANVAS_H_PT).toFixed(2)}pt`,
    )
    assert.ok(
      Math.abs(afterEnsure.h - origin.h) * CANVAS_H_PT < 1,
      `${side} ensure 后高度跳变应 <1pt，实际 ${((afterEnsure.h - origin.h) * CANVAS_H_PT).toFixed(2)}pt`,
    )

    const container = findContainerById(pair.tree, pair.containerId)
    assert.ok(container && container.type === 'column', `${side} 应有 column cell`)
    assert.equal(container.gap_pt ?? 0, 0, `${side} cell gap 应为 0`)

    const grows = container.children.map((child) => child.grow ?? 1)
    const restoredGrows = growsFromDividerDrag({
      grows,
      topIndex: pair.index,
      t: side === 'before' ? 0 : 1,
      minTop: side === 'before' ? 0 : 0.05,
      minBottom: side === 'after' ? 0 : 0.05,
    })
    const restoredTree = updateChildGrows(pair.tree, pair.containerId, restoredGrows)
    assert.ok(restoredTree, `${side} 应能写回 grow`)
    const back = solve(restoredTree!).find((p) => p.block_id === 'a')!.rect
    assert.ok(
      Math.abs(back.y - origin.y) * CANVAS_H_PT < 0.5,
      `${side} 拖回后顶边应恢复，gap=${((back.y - origin.y) * CANVAS_H_PT).toFixed(2)}pt`,
    )
    assert.ok(
      Math.abs(back.h - origin.h) * CANVAS_H_PT < 0.5,
      `${side} 拖回后高度应恢复，dh=${((back.h - origin.h) * CANVAS_H_PT).toFixed(2)}pt`,
    )
  }
  console.log('上下 ensure OK：gap=0 包装，可拖回满高')
}

// 纯纵向内收：宽度不变，高度明显变化
{
  const tree: FlexContainer = {
    type: 'column',
    id: 'root',
    gap_pt: 14,
    children: [
      { type: 'block', id: 'leaf-t', block_id: 'title', grow: 0.45, text_style: 'title' },
      { type: 'block', id: 'leaf-b', block_id: 'body', grow: 1.5 },
    ],
  }
  const before = solve(tree).find((p) => p.block_id === 'body')!.rect
  const pair = ensureResizePair(tree, 'body', 'y', 'after')!
  const col = findContainerById(pair.tree, pair.containerId)!
  const grows = col.children.map((c) => c.grow ?? 1)
  const startT = grows.slice(0, pair.index + 1).reduce((a, b) => a + b, 0) / grows.reduce((a, b) => a + b, 0)
  // 往上拖：减小 t，内容变矮
  const dragged = applyVerticalResizeDrag({
    root: pair.tree,
    columnId: pair.containerId,
    topIndex: pair.index,
    colH: before.h,
    startT,
    originY: before.y + before.h,
    pointerY: before.y + before.h * 0.55,
  })
  assert.ok(dragged, '内收应产出新树')
  const after = solve(dragged!).find((p) => p.block_id === 'body')!.rect
  assert.ok(
    Math.abs(after.w - before.w) * CANVAS_W_PT < 0.5,
    `纯 y 内收不应改宽度，dw=${((after.w - before.w) * CANVAS_W_PT).toFixed(2)}`,
  )
  assert.ok(
    (before.h - after.h) * CANVAS_H_PT > 10,
    `内收后高度应明显变矮，dh=${((before.h - after.h) * CANVAS_H_PT).toFixed(1)}`,
  )
  console.log(
    `纵向内收 OK：h ${(before.h * CANVAS_H_PT).toFixed(1)}→${(after.h * CANVAS_H_PT).toFixed(1)}pt，宽不变`,
  )
}

// 末子底边外扩：从上方兄弟偷高，宽度不变
{
  const tree: FlexContainer = {
    type: 'column',
    id: 'root',
    gap_pt: 14,
    children: [
      { type: 'block', id: 'leaf-t', block_id: 'title', grow: 0.8, text_style: 'title' },
      { type: 'block', id: 'leaf-b', block_id: 'body', grow: 1.2 },
    ],
  }
  const before = Object.fromEntries(solve(tree).map((p) => [p.block_id, p.rect]))
  const pair = ensureResizePair(tree, 'body', 'y', 'after')!
  const bodyRect = solve(pair.tree).find((p) => p.block_id === 'body')!.rect
  const col = findContainerById(pair.tree, pair.containerId)!
  const grows = col.children.map((c) => c.grow ?? 1)
  const total = grows.reduce((a, b) => a + b, 0)
  const startT = grows.slice(0, pair.index + 1).reduce((a, b) => a + b, 0) / total
  const dragged = applyVerticalResizeDrag({
    root: pair.tree,
    columnId: pair.containerId,
    topIndex: pair.index,
    colH: bodyRect.h,
    startT,
    originY: bodyRect.y + bodyRect.h,
    // 继续往下外扩
    pointerY: bodyRect.y + bodyRect.h + 0.12,
  })
  assert.ok(dragged, '外扩应产出新树')
  const after = Object.fromEntries(solve(dragged!).map((p) => [p.block_id, p.rect]))
  assert.ok(
    Math.abs(after.body!.w - before.body!.w) * CANVAS_W_PT < 0.5,
    `外扩不应改宽度，dw=${((after.body!.w - before.body!.w) * CANVAS_W_PT).toFixed(2)}`,
  )
  assert.ok(
    (after.body!.h - before.body!.h) * CANVAS_H_PT > 10,
    `外扩后 body 应变高，dh=${((after.body!.h - before.body!.h) * CANVAS_H_PT).toFixed(1)}`,
  )
  assert.ok(
    (before.title!.h - after.title!.h) * CANVAS_H_PT > 5,
    `外扩应从 title 偷高，title dh=${((before.title!.h - after.title!.h) * CANVAS_H_PT).toFixed(1)}`,
  )
  console.log(
    `纵向外扩 OK：body h+${((after.body!.h - before.body!.h) * CANVAS_H_PT).toFixed(1)}pt，title 变矮，宽不变`,
  )
}

// 步骤列末子触底后继续下拉：应能向祖先偷高（装下已有内容）
{
  const tree: FlexContainer = {
    type: 'column',
    id: 'root',
    gap_pt: 14,
    children: [
      { type: 'block', id: 'leaf-t', block_id: 'title', grow: 1.2, text_style: 'title' },
      {
        type: 'column',
        id: 'steps',
        gap_pt: 12,
        grow: 1.5,
        children: [
          { type: 'block', id: 'leaf-1', block_id: 's1', grow: 1 },
          { type: 'block', id: 'leaf-2', block_id: 's2', grow: 1 },
          { type: 'block', id: 'leaf-3', block_id: 's3', grow: 1 },
        ],
      },
    ],
  }
  const before = Object.fromEntries(solve(tree).map((p) => [p.block_id, p.rect]))
  const pair = ensureResizePair(tree, 's3', 'y', 'after')!
  const col = findContainerById(pair.tree, pair.containerId)!
  const grows = col.children.map((c) => c.grow ?? 1)
  const total = grows.reduce((a, b) => a + b, 0)
  const startT = grows.slice(0, pair.index + 1).reduce((a, b) => a + b, 0) / total
  const s3 = solve(pair.tree).find((p) => p.block_id === 's3')!.rect
  // wrap cell 高度 ≈ 原 s3（spacer seed 极小）；指针再下移 0.2 触发祖先偷高
  const dragged = applyVerticalResizeDrag({
    root: pair.tree,
    columnId: pair.containerId,
    topIndex: pair.index,
    colH: Math.max(s3.h, 0.05),
    startT,
    originY: s3.y + s3.h,
    pointerY: s3.y + s3.h + 0.2,
  })
  assert.ok(dragged, '触底外扩应产出新树')
  const after = Object.fromEntries(solve(dragged!).map((p) => [p.block_id, p.rect]))
  assert.ok(
    (after.s3!.h - before.s3!.h) * CANVAS_H_PT > 15,
    `末步触底后应能明显长高，dh=${((after.s3!.h - before.s3!.h) * CANVAS_H_PT).toFixed(1)}`,
  )
  assert.ok(
    (before.s2!.h - after.s2!.h) * CANVAS_H_PT > 5,
    `应先向同列上一项偷高，s2 dh=${((before.s2!.h - after.s2!.h) * CANVAS_H_PT).toFixed(1)}`,
  )
  console.log(
    `触底外扩 OK：s3 h+${((after.s3!.h - before.s3!.h) * CANVAS_H_PT).toFixed(1)}pt，s2 变矮`,
  )
}

// 提交前归一：邻块被压到内容软下限时后端会抬回 GROW_MIN，前端先归一，松手后才不会再跳一次
{
  const tree: FlexContainer = {
    type: 'column',
    id: 'root',
    gap_pt: 14,
    children: [
      { type: 'block', id: 'leaf-t', block_id: 'title', grow: 0.5, text_style: 'title' },
      { type: 'block', id: 'leaf-b', block_id: 'body', grow: 1.5 },
      { type: 'block', id: 'leaf-p', block_id: 'pic', grow: 1 },
    ],
  }
  const rects = (t: FlexContainer) =>
    Object.fromEntries(solve(t).map((p) => [p.block_id, p.rect]))
  const before = rects(tree)
  const pair = ensureResizePair(tree, 'body', 'y', 'after')!
  const col = findContainerById(pair.tree, pair.containerId)!
  const grows = col.children.map((c) => c.grow ?? 1)
  const total = grows.reduce((a, b) => a + b, 0)
  const startT = grows.slice(0, pair.index + 1).reduce((a, b) => a + b, 0) / total
  const body = before.body!
  const draft = applyVerticalResizeDrag({
    root: pair.tree,
    columnId: pair.containerId,
    topIndex: pair.index,
    colH: before.pic!.y + before.pic!.h - before.title!.y,
    startT,
    originY: body.y + body.h,
    pointerY: body.y + body.h + 0.25,
  })!
  const normalized = normalizeGrows(draft)

  const squeezed = (findContainerById(draft, 'root')!.children[2]!.grow ?? 1)
  assert.ok(squeezed < GROW_MIN, `用例需覆盖越下限的草稿，实际 grow=${squeezed}`)
  for (const child of findContainerById(normalized, 'root')!.children) {
    assert.ok(
      (child.grow ?? 1) >= GROW_MIN,
      `归一后内容块 grow 不应低于 ${GROW_MIN}，实际 ${child.grow}`,
    )
  }
  // 后端同款算法在重标一轮后会有 1ULP 级抖动，几何上必须稳定：再归一不该看得出动
  const settled = rects(normalizeGrows(normalized))
  for (const [blockId, rect] of Object.entries(rects(normalized))) {
    const drift = Math.abs(settled[blockId]!.h - rect.h) * CANVAS_H_PT
    assert.ok(drift < 0.01, `${blockId} 再归一后高度不应变化，drift=${drift}pt`)
  }
  console.log(
    `提交前归一 OK：pic grow ${squeezed.toFixed(3)}→${(
      findContainerById(normalized, 'root')!.children[2]!.grow ?? 1
    ).toFixed(3)}，再归一不变`,
  )
}

// 嵌套双列底边上拉：包出的拉伸单元格必须留在预览树里，后端摊平规则同样会保留它
{
  const tree: FlexContainer = {
    type: 'column',
    id: 'root',
    gap_pt: 14,
    children: [
      { type: 'block', id: 'leaf-t', block_id: 'title', grow: 0.45, text_style: 'title' },
      {
        type: 'row',
        id: 'main',
        gap_pt: 16,
        grow: 2,
        ratios: [62, 38],
        children: [
          {
            type: 'column',
            id: 'left',
            gap_pt: 12,
            grow: 1,
            children: [
              {
                type: 'row',
                id: 'points',
                gap_pt: 12,
                grow: 1.5,
                ratios: [50, 50],
                children: [
                  { type: 'block', id: 'leaf-bl', block_id: 'body_left', grow: 1 },
                  { type: 'block', id: 'leaf-br', block_id: 'body_right', grow: 1 },
                ],
              },
            ],
          },
          { type: 'block', id: 'leaf-pic', block_id: 'picture', grow: 1 },
        ],
      },
    ],
  }

  const before = solve(tree).find((p) => p.block_id === 'body_left')!.rect
  const pair = ensureResizePair(tree, 'body_left', 'y', 'after')!
  const col = findContainerById(pair.tree, pair.containerId)!
  const grows = col.children.map((c) => c.grow ?? 1)
  const startT =
    grows.slice(0, pair.index + 1).reduce((a, b) => a + b, 0) / grows.reduce((a, b) => a + b, 0)
  const dragged = applyVerticalResizeDrag({
    root: pair.tree,
    columnId: pair.containerId,
    topIndex: pair.index,
    colH: before.h,
    startT,
    originY: before.y + before.h,
    pointerY: before.y + before.h * 0.4,
  })!
  const preview = normalizeGrows(dragged)

  const cell = findContainerById(preview, pair.containerId)!
  assert.ok(
    cell.children.some((child) => child.id.startsWith('spacer-')),
    '拉伸单元格里的占位块必须保留，否则保存后会弹回满行高',
  )
  const after = solve(preview).find((p) => p.block_id === 'body_left')!.rect
  assert.ok(
    (before.h - after.h) * CANVAS_H_PT > 10,
    `深树上拉应明显变矮，dh=${((before.h - after.h) * CANVAS_H_PT).toFixed(1)}`,
  )
  const settled = solve(normalizeGrows(preview)).find((p) => p.block_id === 'body_left')!.rect
  assert.ok(
    Math.abs(settled.h - after.h) * CANVAS_H_PT < 0.01,
    `再归一后高度不应变化，drift=${(Math.abs(settled.h - after.h) * CANVAS_H_PT).toFixed(3)}pt`,
  )
  console.log(
    `嵌套双列上拉 OK：body_left h ${(before.h * CANVAS_H_PT).toFixed(1)}→${(
      after.h * CANVAS_H_PT
    ).toFixed(1)}pt，占位块保留`,
  )
}

console.log('\nflex edit check 全部通过')
