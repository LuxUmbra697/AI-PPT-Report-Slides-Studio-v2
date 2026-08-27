import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { type DeckSlide, slideDisplayTitle } from '@/features/deck/types'

export function DeleteSlideDialog({
  slide,
  slideCount,
  pending,
  onClose,
  onConfirm,
}: {
  slide: DeckSlide
  slideCount: number
  pending: boolean
  onClose: () => void
  onConfirm: () => void
}) {
  return (
    <Dialog
      title="删除这一页？"
      description={`「${slideDisplayTitle(slide)}」及其内容会一并删除，且无法撤销。`}
      className="max-w-sm"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onClose}>
            取消
          </Button>
          <Button
            size="sm"
            className="bg-negative hover:bg-negative/90 disabled:hover:bg-negative"
            disabled={pending}
            onClick={onConfirm}
          >
            {pending ? '删除中…' : '删除'}
          </Button>
        </>
      }
    >
      <p className="text-[13px] text-ink-soft">
        当前共 {slideCount} 页，删除后剩 {slideCount - 1} 页。
      </p>
    </Dialog>
  )
}
