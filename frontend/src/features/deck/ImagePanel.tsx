import { ImageIcon, Upload } from 'lucide-react'
import { type ChangeEvent, useRef } from 'react'
import { useReplaceSlideImage } from '@/features/deck/api'
import { ACCEPTED_IMAGE, type DeckSlide, imageBlocks } from '@/features/deck/types'
import { errorMessage } from '@/lib/errors'
import type { ImageBlock } from '@/render/types'

const SOURCE_LABEL: Record<ImageBlock['source'], string> = {
  generated: 'AI 生成',
  stock: '图库',
  upload: '手动上传',
  placeholder: '占位图',
}

export function ImagePanel({
  projectId,
  slide,
  disabled,
}: {
  projectId: string
  slide: DeckSlide
  disabled?: boolean
}) {
  const images = imageBlocks(slide)

  if (images.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-line-strong px-4 py-8 text-center">
        <ImageIcon className="mx-auto mb-2 size-4 text-ink-muted" />
        <p className="text-[13px] text-ink-muted">这一页的版式里没有图片位</p>
        <p className="mt-1 text-xs text-ink-muted">换一个带图的版式即可放图</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {images.map((block, index) => (
        <ImageSlot
          key={block.id}
          projectId={projectId}
          slide={slide}
          block={block}
          label={images.length > 1 ? `图片 ${index + 1}` : '图片'}
          disabled={disabled}
        />
      ))}
    </div>
  )
}

function ImageSlot({
  projectId,
  slide,
  block,
  label,
  disabled,
}: {
  projectId: string
  slide: DeckSlide
  block: ImageBlock
  label: string
  disabled?: boolean
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const replace = useReplaceSlideImage(projectId)

  const pick = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    // 清空，否则连续选择同一个文件不会再触发 change
    event.target.value = ''
    if (file) {
      replace.mutate({ slideId: slide.id, blockId: block.id, revision: slide.revision, file })
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[13px] font-medium">{label}</span>
        <span className="text-xs text-ink-muted">{SOURCE_LABEL[block.source]}</span>
      </div>

      <div className="overflow-hidden rounded-xl border border-line bg-surface-soft">
        {block.url ? (
          <img src={block.url} alt={block.alt} className="aspect-video w-full object-cover" />
        ) : (
          <div className="grid aspect-video place-items-center text-ink-muted">
            <ImageIcon className="size-5" />
          </div>
        )}
      </div>

      <button
        type="button"
        disabled={disabled || replace.isPending}
        onClick={() => inputRef.current?.click()}
        className="flex items-center justify-center gap-1.5 rounded-full border border-line py-2 text-[13px] text-ink-soft transition-colors hover:border-line-strong hover:text-ink disabled:opacity-50"
      >
        <Upload className="size-3.5" />
        {replace.isPending ? '上传中…' : '替换图片'}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_IMAGE}
        onChange={pick}
        aria-label={`${label}：上传 PNG、JPEG 或 WebP`}
        className="sr-only"
      />

      {/* 图库授权要求标注作者：放在编辑侧栏而不是页面里，既满足要求也不占版面 */}
      {block.credit && <p className="text-xs leading-relaxed text-ink-muted">{block.credit}</p>}
      {replace.isError && (
        <p role="alert" className="text-xs text-negative">
          {errorMessage(replace.error, '换图失败')}
        </p>
      )}
    </div>
  )
}
