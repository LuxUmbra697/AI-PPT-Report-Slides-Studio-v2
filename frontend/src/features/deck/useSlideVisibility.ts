import { useEffect, useRef } from 'react'
import type { DeckSlide } from '@/features/deck/types'

/**
 * 滚动容器内按可见比例跟踪当前页；胶片条 / 导出定位时短暂忽略 observer。
 */
export function useSlideVisibility({
  slides,
  scrollRequest,
  onActiveChange,
}: {
  slides: DeckSlide[]
  scrollRequest: { id: string; nonce: number } | null
  onActiveChange: (slideId: string) => void
}) {
  const scrollerRef = useRef<HTMLDivElement>(null)
  const slideElsRef = useRef(new Map<string, HTMLElement>())
  const ignoreObserverRef = useRef(false)
  const slideIdsKey = slides.map((slide) => slide.id).join('|')

  const bindSlideEl = (slideId: string, node: HTMLElement | null) => {
    if (node) slideElsRef.current.set(slideId, node)
    else slideElsRef.current.delete(slideId)
  }

  // 胶片条 / 导出定位：滚到目标页；滚动过程中忽略 observer，避免中间页抢焦点
  useEffect(() => {
    if (!scrollRequest) return
    const node = slideElsRef.current.get(scrollRequest.id)
    if (!node) return
    ignoreObserverRef.current = true
    node.scrollIntoView({ behavior: 'smooth', block: 'center' })
    const timer = window.setTimeout(() => {
      ignoreObserverRef.current = false
    }, 450)
    return () => window.clearTimeout(timer)
  }, [scrollRequest])

  useEffect(() => {
    const root = scrollerRef.current
    if (!root) return

    const ratios = new Map<string, number>()
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const id = (entry.target as HTMLElement).dataset.slideId
          if (!id) continue
          if (entry.isIntersecting) ratios.set(id, entry.intersectionRatio)
          else ratios.delete(id)
        }
        if (ignoreObserverRef.current || ratios.size === 0) return
        let bestId: string | null = null
        let bestRatio = 0
        for (const [id, ratio] of ratios) {
          if (ratio > bestRatio) {
            bestRatio = ratio
            bestId = id
          }
        }
        if (bestId) onActiveChange(bestId)
      },
      { root, threshold: [0.25, 0.45, 0.65, 0.85], rootMargin: '-12% 0px -12% 0px' },
    )

    const nodes = Array.from(root.querySelectorAll<HTMLElement>('[data-slide-id]'))
    for (const node of nodes) {
      slideElsRef.current.set(node.dataset.slideId!, node)
      observer.observe(node)
    }
    return () => observer.disconnect()
  }, [slideIdsKey, onActiveChange])

  return { scrollerRef, bindSlideEl }
}
