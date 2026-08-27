import { useEffect, useId, useRef, useState } from 'react'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { useApplyAiEdit, useProposeAiEdit } from '@/features/deck/api'
import type {
  AiEditOperation,
  AiEditProposal,
  DeckSlide,
} from '@/features/deck/types'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

const TYPE_LABEL: Record<string, string> = {
  text: '文字',
  bullets: '列表',
  kpi: '指标',
  table: '表格',
  cards: '卡片',
  callout: '提示',
  image: '图片',
  chart: '图表',
}

const OP_LABEL: Record<string, string> = {
  replace: '替换',
  add: '新增',
  delete: '删除',
  change_type: '改类型',
}

type ActiveSide = 'before' | 'after'

type ChatTurn = {
  id: string
  instruction: string
  proposal: AiEditProposal | null
  error: string | null
}

function newTurnId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export function AiEditPanel({
  projectId,
  slide,
}: {
  projectId: string
  slide: DeckSlide
}) {
  const titleId = useId()
  const inputId = useId()
  const listRef = useRef<HTMLDivElement>(null)
  const [draft, setDraft] = useState('')
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [activeSide, setActiveSide] = useState<Record<string, ActiveSide>>({})
  const [workingRevision, setWorkingRevision] = useState(slide.revision)
  const [applyingBlockId, setApplyingBlockId] = useState<string | null>(null)
  const [applyError, setApplyError] = useState<string | null>(null)
  const [applyConflict, setApplyConflict] = useState(false)

  const propose = useProposeAiEdit(projectId, slide.id)
  const apply = useApplyAiEdit(projectId, slide.id)

  const generating = slide.status === 'generating'
  const busy = propose.isPending || applyingBlockId != null
  const isFlex = slide.layout_mode === 'flex'
  const editableUnlocked = slide.blocks.some(
    (block) => !block.locked && block.type in TYPE_LABEL,
  )
  const canPropose = !generating && !busy && (editableUnlocked || isFlex)
  const trimmedDraft = draft.trim()
  const canSend = canPropose && trimmedDraft.length > 0

  const latestProposal =
    [...turns].reverse().find((turn) => turn.proposal != null)?.proposal ?? null
  const lastInstruction =
    [...turns].reverse().find((turn) => turn.instruction)?.instruction ?? null

  useEffect(() => {
    // 换页时清掉对话与提案，避免把旧页操作套到新页
    setDraft('')
    setTurns([])
    setActiveSide({})
    setWorkingRevision(slide.revision)
    setApplyingBlockId(null)
    setApplyError(null)
    setApplyConflict(false)
  }, [slide.id])

  useEffect(() => {
    const node = listRef.current
    if (!node) return
    node.scrollTop = node.scrollHeight
  }, [turns, propose.isPending])

  const clearProposalSegments = () => {
    setTurns((current) =>
      current.map((turn) => ({ ...turn, proposal: null, error: null })),
    )
    setActiveSide({})
    setApplyError(null)
    setApplyConflict(false)
    apply.reset()
    propose.reset()
  }

  const sendInstruction = (instruction: string) => {
    if (!canPropose || !instruction) return
    const turnId = newTurnId()
    setApplyError(null)
    setApplyConflict(false)
    apply.reset()
    // 新一轮提案替换当前预览；用户气泡保留
    setTurns((current) => [
      ...current.map((turn) => ({ ...turn, proposal: null, error: null })),
      { id: turnId, instruction, proposal: null, error: null },
    ])
    setActiveSide({})
    setDraft('')
    propose.mutate(
      {
        revision: slide.revision,
        instruction: instruction.slice(0, 500),
        history: turns
          .filter((turn) => turn.instruction.trim())
          .slice(-5)
          .map((turn) => ({
            instruction: turn.instruction.slice(0, 500),
            note: turn.proposal
              ? `改了 ${turn.proposal.operations.length} 处`
              : null,
          })),
      },
      {
        onSuccess: (data) => {
          setWorkingRevision(data.revision)
          setTurns((current) =>
            current.map((turn) =>
              turn.id === turnId ? { ...turn, proposal: data, error: null } : turn,
            ),
          )
        },
        onError: (error) => {
          setTurns((current) =>
            current.map((turn) =>
              turn.id === turnId
                ? { ...turn, proposal: null, error: errorMessage(error) }
                : turn,
            ),
          )
        },
      },
    )
  }

  const handleSend = () => {
    if (!canSend) return
    sendInstruction(trimmedDraft)
  }

  const applySide = (operation: AiEditOperation, side: ActiveSide) => {
    if (applyingBlockId != null || generating) return
    if (activeSide[operation.block_id] === side) return

    const snapshot = asSnapshot(side === 'after' ? operation.after : operation.before)
    const op = operation.op ?? 'replace'
    setApplyingBlockId(operation.block_id)
    setApplyError(null)
    setApplyConflict(false)
    apply.mutate(
      {
        revision: workingRevision,
        op,
        block_id: operation.block_id,
        after_block_id: operation.after_block_id ?? null,
        side,
        replace: op === 'replace' ? snapshot : null,
        block: op === 'replace' ? null : snapshot,
      },
      {
        onSuccess: (updated) => {
          setWorkingRevision(updated.revision)
          setActiveSide((current) => ({ ...current, [operation.block_id]: side }))
          setApplyingBlockId(null)
        },
        onError: (error) => {
          setApplyingBlockId(null)
          setApplyError(errorMessage(error))
          setApplyConflict(error instanceof ApiError && error.status === 409)
        },
      },
    )
  }

  return (
    <section aria-labelledby={titleId} className="flex h-full min-h-0 flex-col gap-3">
      <div>
        <h3 id={titleId} className="text-sm font-semibold tracking-tight">
          AI 修改这一页
        </h3>
        <p className="mt-1 text-xs leading-relaxed text-ink-muted">
          用自然语言描述想改的内容；点选改动前/后即可应用到画布
        </p>
      </div>

      {generating && <p className="text-xs text-ink-muted">页面生成中，暂不可发起 AI 修改</p>}

      {!generating && !editableUnlocked && !isFlex && (
        <p className="rounded-xl border border-dashed border-line px-3 py-3 text-xs leading-relaxed text-ink-muted">
          本页可编辑内容均已人工修改，AI 不会覆盖；如需改写请先手动调整或换一页。
        </p>
      )}

      <div
        ref={listRef}
        className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-0.5"
      >
        {turns.length === 0 && !propose.isPending && (
          <p className="rounded-xl border border-dashed border-line px-3 py-4 text-xs leading-relaxed text-ink-muted">
            例如：「标题改得更正式」「正文压缩到三条」「语气更适合管理层」
          </p>
        )}

        {turns.map((turn) => (
          <div key={turn.id} className="flex flex-col gap-2">
            <div className="flex justify-end">
              <p className="max-w-[92%] rounded-2xl rounded-br-md bg-accent-soft px-3 py-2 text-[13px] leading-relaxed text-ink">
                {turn.instruction}
              </p>
            </div>
            {turn.error && (
              <p role="alert" className="rounded-xl bg-negative/8 px-3 py-2 text-xs text-negative">
                {turn.error}
              </p>
            )}
            {turn.proposal && (
              <ProposalPreview
                proposal={turn.proposal}
                activeSide={activeSide}
                applyingBlockId={applyingBlockId}
                applyError={applyError}
                applyConflict={applyConflict}
                onApplySide={applySide}
                onDiscard={clearProposalSegments}
                onRegenerate={() => lastInstruction && sendInstruction(lastInstruction)}
                canRegenerate={canPropose && lastInstruction != null}
              />
            )}
          </div>
        ))}

        {propose.isPending && (
          <p className="text-xs text-ink-muted" aria-live="polite">
            正在根据指令生成提案…
          </p>
        )}
      </div>

      <div className="flex flex-col gap-2 border-t border-line pt-3">
        <label htmlFor={inputId} className="sr-only">
          修改指令
        </label>
        <textarea
          id={inputId}
          value={draft}
          maxLength={500}
          rows={2}
          disabled={busy || generating || !(editableUnlocked || isFlex)}
          placeholder="输入修改指令，回车发送"
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              handleSend()
            }
          }}
          className={cn(
            'rounded-xl border border-line bg-surface px-3 py-2 text-[13px] leading-relaxed text-ink',
            'placeholder:text-ink-muted/70 focus:border-accent focus:outline-none',
            'resize-none disabled:opacity-40',
          )}
        />
        <div className="flex items-center justify-between gap-2">
          <p className="text-[11px] text-ink-muted">{draft.trim().length}/500</p>
          <Button size="sm" disabled={!canSend} onClick={handleSend}>
            {propose.isPending ? '发送中…' : '发送'}
          </Button>
        </div>
      </div>

      {latestProposal == null && applyError && (
        <p role="alert" className="text-xs text-negative">
          {applyError}
        </p>
      )}
    </section>
  )
}

function ProposalPreview({
  proposal,
  activeSide,
  applyingBlockId,
  applyError,
  applyConflict,
  onApplySide,
  onDiscard,
  onRegenerate,
  canRegenerate,
}: {
  proposal: AiEditProposal
  activeSide: Record<string, ActiveSide>
  applyingBlockId: string | null
  applyError: string | null
  applyConflict: boolean
  onApplySide: (operation: AiEditOperation, side: ActiveSide) => void
  onDiscard: () => void
  onRegenerate: () => void
  canRegenerate: boolean
}) {
  const listId = useId()
  const empty = proposal.operations.length === 0

  return (
    <section
      aria-labelledby={listId}
      className="rounded-2xl rounded-tl-md border border-line bg-surface px-3 py-3"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h4 id={listId} className="text-xs font-semibold text-ink-soft">
          变更预览
        </h4>
        <Button variant="ghost" size="sm" disabled={applyingBlockId != null} onClick={onDiscard}>
          放弃
        </Button>
      </div>

      {empty ? (
        <p className="rounded-xl border border-dashed border-line px-3 py-4 text-xs leading-relaxed text-ink-muted">
          模型没有提出需要修改的内容
          {proposal.discarded.length > 0
            ? '（部分块因已人工修改等原因被跳过）'
            : '。可调整指令后重试。'}
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {proposal.operations.map((op) => (
            <OperationCard
              key={op.block_id}
              operation={op}
              side={activeSide[op.block_id] ?? null}
              applying={applyingBlockId === op.block_id}
              disabled={applyingBlockId != null}
              onSelectSide={(side) => onApplySide(op, side)}
            />
          ))}
        </ul>
      )}

      {proposal.warnings.length > 0 && (
        <div className="mt-3 rounded-xl bg-warning/8 px-3 py-2.5">
          <p className="mb-1 text-xs font-medium text-warning">应用后可能出现</p>
          <ul className="flex flex-col gap-1">
            {proposal.warnings.map((issue, index) => (
              <li key={`${issue.slot_id ?? 'page'}-${index}`} className="text-xs text-warning">
                {issue.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {proposal.discarded.length > 0 && (
        <div className="mt-3 rounded-xl bg-surface-soft px-3 py-2.5">
          <p className="mb-1 text-xs font-medium text-ink-soft">未改动的内容</p>
          <ul className="flex flex-col gap-1.5">
            {proposal.discarded.map((item) => (
              <li key={item.block_id} className="text-xs leading-relaxed text-ink-muted">
                {item.reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      {!empty && (
        <p className="mt-3 text-xs text-ink-muted">点击「改动前 / 改动后」即可应用到画布，可来回切换</p>
      )}

      {applyError && (
        <div role="alert" className="mt-3 rounded-xl bg-negative/8 px-3 py-2.5">
          <p className="text-xs text-negative">{applyError}</p>
          {applyConflict && (
            <button
              type="button"
              disabled={!canRegenerate}
              onClick={onRegenerate}
              className="mt-2 text-xs text-ink-muted underline-offset-2 hover:text-accent hover:underline disabled:opacity-40"
            >
              刷新提案
            </button>
          )}
        </div>
      )}
    </section>
  )
}

function OperationCard({
  operation,
  side,
  applying,
  disabled,
  onSelectSide,
}: {
  operation: AiEditOperation
  side: ActiveSide | null
  applying: boolean
  disabled?: boolean
  onSelectSide: (side: ActiveSide) => void
}) {
  const typeLabel = TYPE_LABEL[operation.type] ?? operation.type
  const opLabel = OP_LABEL[operation.op ?? 'replace'] ?? operation.op
  return (
    <li className="overflow-hidden rounded-xl border border-line">
      <div className="flex items-center gap-3 border-b border-line bg-surface-soft px-3 py-2">
        <div className="min-w-0 flex-1">
          <span className="text-[10px] tracking-[0.16em] text-accent uppercase">
            {typeLabel}
          </span>
          <span className="ml-2 text-[11px] text-ink-soft">{opLabel}</span>
          <span className="ml-2 text-[11px] text-ink-soft">{operation.slot_id}</span>
        </div>
        {applying && <span className="text-[11px] text-ink-muted">应用中…</span>}
      </div>
      <div className="grid gap-0 sm:grid-cols-2">
        <PatchSide
          label="改动前"
          tone="before"
          patch={asSnapshot(operation.before)}
          type={operation.type}
          emptyHint={operation.op === 'add' ? '（将新增）' : '（空）'}
          active={side === 'before'}
          disabled={disabled}
          onSelect={() => onSelectSide('before')}
        />
        <PatchSide
          label="改动后"
          tone="after"
          patch={asSnapshot(operation.after)}
          type={operation.type}
          emptyHint={operation.op === 'delete' ? '（将删除）' : '（空）'}
          active={side === 'after'}
          disabled={disabled}
          onSelect={() => onSelectSide('after')}
        />
      </div>
    </li>
  )
}

function PatchSide({
  label,
  tone,
  patch,
  type,
  emptyHint,
  active,
  disabled,
  onSelect,
}: {
  label: string
  tone: ActiveSide
  patch: Record<string, unknown> | null
  type: string
  emptyHint: string
  active: boolean
  disabled?: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      disabled={disabled || active}
      onClick={onSelect}
      aria-pressed={active}
      className={cn(
        'px-3 py-3 text-left transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:ring-inset',
        'disabled:cursor-default',
        !active && !disabled && 'hover:bg-accent-soft/40 cursor-pointer',
        tone === 'before' && 'border-b border-line sm:border-r sm:border-b-0',
        active && tone === 'before' && 'bg-surface-soft',
        active && tone === 'after' && 'bg-accent-soft/50',
        !active && tone === 'after' && 'sm:border-l-2 sm:border-l-transparent',
        active && tone === 'after' && 'sm:border-l-2 sm:border-l-accent',
      )}
    >
      <p
        className={cn(
          'mb-2 text-[10px] tracking-[0.16em] uppercase',
          active
            ? tone === 'before'
              ? 'text-ink-soft'
              : 'text-accent'
            : tone === 'before'
              ? 'text-ink-muted'
              : 'text-accent/80',
        )}
      >
        {label}
        {active ? ' · 已应用' : ''}
      </p>
      <div
        className={cn(
          'text-xs leading-relaxed',
          tone === 'before' && !active && 'text-ink-muted line-through decoration-ink-muted/50 opacity-70',
          tone === 'before' && active && 'text-ink',
          tone === 'after' && 'text-ink',
        )}
      >
        <PatchContent patch={patch} type={type} emptyHint={emptyHint} />
      </div>
    </button>
  )
}

function asText(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function asSnapshot(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }
  return null
}

function asStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => (typeof item === 'string' ? item : String(item))) : []
}

function PatchContent({
  patch,
  type,
  emptyHint,
}: {
  patch: Record<string, unknown> | null
  type: string
  emptyHint: string
}) {
  if (patch == null) {
    return <p>{emptyHint}</p>
  }

  const kind = asText(patch.type) || type

  if (kind === 'text') {
    return <p className="whitespace-pre-wrap">{asText(patch.text) || '（空）'}</p>
  }

  if (kind === 'bullets') {
    const items = asStringList(patch.items)
    if (items.length === 0) return <p>（空列表）</p>
    return (
      <ul className="flex flex-col gap-1">
        {items.map((item, index) => (
          <li key={`${index}-${item.slice(0, 12)}`} className="flex gap-2">
            <span className="text-ink-soft tabular-nums">{String(index + 1).padStart(2, '0')}</span>
            <span className="min-w-0 flex-1 whitespace-pre-wrap">{item}</span>
          </li>
        ))}
      </ul>
    )
  }

  if (kind === 'kpi') {
    return (
      <dl className="flex flex-col gap-1.5">
        <div>
          <dt className="text-[10px] text-ink-soft">数值</dt>
          <dd>{asText(patch.value) || '—'}</dd>
        </div>
        <div>
          <dt className="text-[10px] text-ink-soft">标签</dt>
          <dd>{asText(patch.label) || '—'}</dd>
        </div>
        <div>
          <dt className="text-[10px] text-ink-soft">备注</dt>
          <dd>{asText(patch.note).trim() ? asText(patch.note) : '—'}</dd>
        </div>
      </dl>
    )
  }

  if (kind === 'table') {
    const header = asStringList(patch.header)
    const rows = Array.isArray(patch.rows)
      ? patch.rows.map((row) => (Array.isArray(row) ? row.map((cell) => String(cell ?? '')) : []))
      : []
    return (
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr>
              {header.map((cell, index) => (
                <th
                  key={`h-${index}`}
                  className="border-b border-line px-1.5 py-1 font-medium"
                >
                  {cell || '—'}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={`r-${rowIndex}`}>
                {row.map((cell, cellIndex) => (
                  <td key={`c-${rowIndex}-${cellIndex}`} className="border-b border-line/60 px-1.5 py-1">
                    {cell || '—'}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  if (kind === 'cards') {
    const items = Array.isArray(patch.items) ? patch.items : []
    if (items.length === 0) return <p>（空卡片）</p>
    return (
      <ul className="flex flex-col gap-2">
        {items.map((raw, index) => {
          const item = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
          const title = asText(item.title)
          return (
            <li key={`${index}-${title.slice(0, 12)}`} className="flex flex-col gap-0.5">
              <span className="font-medium">
                {asText(item.icon) ? `${asText(item.icon)} ` : ''}
                {title || '—'}
              </span>
              <span className="whitespace-pre-wrap text-ink-soft">{asText(item.desc) || '—'}</span>
            </li>
          )
        })}
      </ul>
    )
  }

  if (kind === 'callout') {
    return (
      <p className="whitespace-pre-wrap">
        {asText(patch.icon) ? `${asText(patch.icon)} ` : ''}
        {asText(patch.text) || '（空）'}
        <span className="ml-2 text-[10px] text-ink-soft">[{asText(patch.variant) || 'note'}]</span>
      </p>
    )
  }

  if (kind === 'image') {
    return <p>{asText(patch.alt) || '图片占位'}</p>
  }

  if (kind === 'chart') {
    return <p>图表</p>
  }

  return <p>（无法展示）</p>
}

