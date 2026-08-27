import { Download, MoreHorizontal, Play, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { MenuItem, MenuPopover } from '@/components/ui/MenuPopover'
import { cn } from '@/lib/utils'
import type { DeckSlide } from '@/features/deck/types'

export function EditorHeaderActions({
  slides,
  failed,
  deckStatus,
  generatePending,
  onContinueGenerate,
  onPresent,
  onExport,
  onRegenerateAll,
}: {
  slides: DeckSlide[]
  failed: number
  deckStatus: string | undefined
  generatePending: boolean
  onContinueGenerate: () => void
  onPresent: () => void
  onExport: () => void
  onRegenerateAll: () => void
}) {
  return (
    <>
      {(deckStatus === 'partial' || failed > 0) && (
        <Button
          variant="ghost"
          size="sm"
          disabled={generatePending}
          onClick={onContinueGenerate}
        >
          <RefreshCw className={cn('size-3.5', generatePending && 'animate-spin')} />
          继续生成
        </Button>
      )}
      <Button
        variant="ghost"
        size="sm"
        disabled={!slides.some((slide) => slide.status === 'ready')}
        onClick={onPresent}
      >
        <Play className="size-3.5" />
        演示
      </Button>
      <Button size="sm" disabled={slides.length === 0} onClick={onExport}>
        <Download className="size-4" />
        导出
      </Button>
      {slides.length > 0 && (
        <OverflowMenu
          disabled={generatePending}
          onRegenerateAll={onRegenerateAll}
        />
      )}
    </>
  )
}

function OverflowMenu({
  disabled,
  onRegenerateAll,
}: {
  disabled?: boolean
  onRegenerateAll: () => void
}) {
  return (
    <MenuPopover
      label="更多操作"
      className="w-52"
      trigger={({ open, toggle }) => (
        <button
          type="button"
          aria-label="更多操作"
          aria-expanded={open}
          onClick={toggle}
          className="grid size-8 place-items-center rounded-lg text-ink-muted transition-colors hover:bg-surface-soft hover:text-ink"
        >
          <MoreHorizontal className="size-4" />
        </button>
      )}
    >
      {({ close }) => (
        <MenuItem
          disabled={disabled}
          hint="会覆盖所有页面的现有内容"
          onSelect={() => {
            close()
            onRegenerateAll()
          }}
        >
          全部重新生成
        </MenuItem>
      )}
    </MenuPopover>
  )
}
