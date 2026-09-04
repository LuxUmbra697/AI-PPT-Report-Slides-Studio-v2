import { API_PREFIX } from '@/api/client'
import type { CSSProperties } from 'react'
import type {
  ExternalTemplateElement,
  ExternalTemplateInspection,
} from '@/features/templates/api'

export interface ExternalTemplateLayerSource {
  templateId: string
  inspection: ExternalTemplateInspection
}

function isVisual(element: ExternalTemplateElement): boolean {
  if (element.kind === 'picture') return element.asset_id != null
  if (element.kind === 'line') return true
  return (
    element.kind === 'shape' &&
    !element.text_preview &&
    (element.source_layer !== 'slide' ||
      element.role === '背景色块' ||
      element.role === '点缀图案')
  )
}

function elementStyle(element: ExternalTemplateElement): CSSProperties {
  return {
    position: 'absolute',
    left: `${element.rect.left * 100}%`,
    top: `${element.rect.top * 100}%`,
    width: `${element.rect.width * 100}%`,
    height: `${element.rect.height * 100}%`,
  }
}

/** Source master/layout/slide graphics placed below the app's editable content blocks. */
export function ExternalTemplateLayer({
  source,
  slideIndex,
}: {
  source: ExternalTemplateLayerSource
  slideIndex: number
}) {
  const sourceSlide = source.inspection.slides[
    Math.min(slideIndex, source.inspection.slides.length - 1)
  ]
  if (!sourceSlide) return null
  const elements = sourceSlide.elements.filter(isVisual)

  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 z-0 overflow-hidden">
      {elements.map((element) => {
        if (element.kind === 'picture' && element.asset_id) {
          const asset = encodeURIComponent(element.asset_id)
          return (
            <img
              key={element.id}
              src={`${API_PREFIX}/design/external-templates/${encodeURIComponent(source.templateId)}/assets/${asset}`}
              alt=""
              draggable={false}
              style={{ ...elementStyle(element), objectFit: 'fill' }}
            />
          )
        }
        const color = element.colors[0]
        if (!color) return null
        return <div key={element.id} style={{ ...elementStyle(element), background: color }} />
      })}
    </div>
  )
}
