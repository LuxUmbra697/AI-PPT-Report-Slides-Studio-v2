import { useLayoutEffect, useRef, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  XAxis,
  YAxis,
} from 'recharts'
import { resolveColor, webFontStack } from '@/render/style'
import {
  CANVAS_HEIGHT_PT,
  CANVAS_WIDTH_PT,
  type ChartBlock,
  type Slot,
  type Theme,
} from '@/render/types'

/**
 * 幻灯片其余部分靠 cqw 等比缩放，而 Recharts 的字号、描边、边距都是像素数，
 * 不会跟着容器变。因此这里量出实际像素宽度换算成缩放比，把图表画在与 PPTX
 * 相同的 pt 坐标系里再整体缩放——两端的构图比例因此严格一致。
 */
function useSlotScale(widthPt: number) {
  const ref = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(0)

  useLayoutEffect(() => {
    const element = ref.current
    if (!element) return
    const observer = new ResizeObserver(([entry]) => {
      setScale(entry.contentRect.width / widthPt)
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [widthPt])

  return { ref, scale }
}

/** 一次算好图表内所有视觉常量，避免各处重复从主题里翻 */
function chartStyle(theme: Theme, seriesCount: number) {
  const label = theme.text_styles.chart_label
  const text = {
    fontSize: label.size_pt,
    fontFamily: webFontStack(theme.fonts.body),
    fill: resolveColor(theme, label.color),
  }

  return {
    text,
    gridColor: resolveColor(theme, 'line'),
    axisColor: resolveColor(theme, 'line_strong'),
    background: resolveColor(theme, 'background'),
    colors: theme.palette.chart_series,
    // 只有一条系列时图例里也只有一项，纯属噪音
    showLegend: seriesCount > 1,
  }
}

type Style = ReturnType<typeof chartStyle>
type Row = Record<string, string | number>

interface PlotProps {
  block: ChartBlock
  data: Row[]
  style: Style
  width: number
  height: number
}

function toRows(block: ChartBlock): Row[] {
  return block.categories.map((name, index) => {
    const row: Row = { name }
    for (const series of block.series) row[series.name] = series.values[index] ?? 0
    return row
  })
}

function ChartLegend({ style }: { style: Style }) {
  if (!style.showLegend) return null
  return (
    <Legend
      verticalAlign="bottom"
      iconType="square"
      iconSize={style.text.fontSize * 0.8}
      wrapperStyle={{ ...style.text, color: style.text.fill, paddingTop: 4 }}
    />
  )
}

/** 横向网格线足以读数，纵向网格线只会把画面切碎 */
function ChartGrid({ style, vertical = false }: { style: Style; vertical?: boolean }) {
  return (
    <CartesianGrid stroke={style.gridColor} strokeDasharray="0" vertical={vertical} horizontal={!vertical} />
  )
}

function unitLabel(block: ChartBlock, style: Style) {
  if (!block.unit) return undefined
  return { value: block.unit, angle: -90, position: 'insideLeft' as const, style: style.text }
}

function frame(block: ChartBlock, data: Row[], style: Style, width: number, height: number) {
  return {
    width,
    height,
    data,
    margin: { top: 8, right: 8, bottom: style.showLegend ? 0 : 4, left: block.unit ? 4 : 0 },
  }
}

function PiePlot({ block, data, style, width, height }: PlotProps) {
  return (
    <PieChart width={width} height={height}>
      <Pie
        data={data}
        dataKey={block.series[0]?.name ?? 'value'}
        nameKey="name"
        outerRadius="72%"
        isAnimationActive={false}
        label={style.text}
        labelLine={{ stroke: style.axisColor }}
        stroke={style.background}
      >
        {/* 饼图每一片代表一个分类而非一条系列，因此按数据点着色 */}
        {data.map((row, index) => (
          <Cell key={String(row.name)} fill={style.colors[index % style.colors.length]} />
        ))}
      </Pie>
    </PieChart>
  )
}

function LinePlot({ block, data, style, width, height }: PlotProps) {
  return (
    <LineChart {...frame(block, data, style, width, height)}>
      <ChartGrid style={style} />
      <XAxis dataKey="name" tick={style.text} tickLine={false} stroke={style.axisColor} />
      <YAxis tick={style.text} tickLine={false} axisLine={false} label={unitLabel(block, style)} />
      <ChartLegend style={style} />
      {block.series.map((series, index) => (
        <Line
          key={series.name}
          type="monotone"
          dataKey={series.name}
          stroke={style.colors[index % style.colors.length]}
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
      ))}
    </LineChart>
  )
}

function BarPlot({ block, data, style, width, height }: PlotProps) {
  // Recharts 的 layout 指的是数值轴方向：vertical 画出来才是横向条形
  const horizontal = block.chart_type === 'bar'

  return (
    <BarChart
      {...frame(block, data, style, width, height)}
      layout={horizontal ? 'vertical' : 'horizontal'}
    >
      <ChartGrid style={style} vertical={horizontal} />
      {horizontal ? (
        <>
          <XAxis type="number" tick={style.text} tickLine={false} axisLine={false} />
          <YAxis
            type="category"
            dataKey="name"
            tick={style.text}
            tickLine={false}
            stroke={style.axisColor}
            width={Math.min(width * 0.28, 96)}
          />
        </>
      ) : (
        <>
          <XAxis dataKey="name" tick={style.text} tickLine={false} stroke={style.axisColor} />
          <YAxis tick={style.text} tickLine={false} axisLine={false} label={unitLabel(block, style)} />
        </>
      )}
      <ChartLegend style={style} />
      {block.series.map((series, index) => (
        <Bar
          key={series.name}
          dataKey={series.name}
          fill={style.colors[index % style.colors.length]}
          isAnimationActive={false}
          maxBarSize={36}
        />
      ))}
    </BarChart>
  )
}

const PLOTS = {
  pie: PiePlot,
  line: LinePlot,
  bar: BarPlot,
  column: BarPlot,
} as const

export function ChartView({ block, slot, theme }: { block: ChartBlock; slot: Slot; theme: Theme }) {
  const width = slot.rect.w * CANVAS_WIDTH_PT
  const height = slot.rect.h * CANVAS_HEIGHT_PT
  const { ref, scale } = useSlotScale(width)

  const style = chartStyle(theme, block.series.length)
  const Plot = PLOTS[block.chart_type]

  return (
    <div ref={ref} style={{ width: '100%', height: '100%', overflow: 'hidden' }}>
      {scale > 0 && (
        <div
          style={{ width, height, transformOrigin: 'top left', transform: `scale(${scale})` }}
        >
          <Plot block={block} data={toRows(block)} style={style} width={width} height={height} />
        </div>
      )}
    </div>
  )
}
