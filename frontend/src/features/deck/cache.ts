import type { Deck, DeckSlide } from '@/features/deck/types'

/** 用单页响应替换 deck 缓存里对应页，避免 invalidate 冲掉正在编辑的 DOM */
export function replaceSlideInDeck(deck: Deck | undefined, slide: DeckSlide): Deck | undefined {
  if (!deck) return deck
  return {
    ...deck,
    slides: deck.slides.map((item) => (item.id === slide.id ? slide : item)),
  }
}

export function replaceSlidesInDeck(deck: Deck | undefined, slides: DeckSlide[]): Deck | undefined {
  if (!deck) return deck
  return { ...deck, slides, total: slides.length }
}
