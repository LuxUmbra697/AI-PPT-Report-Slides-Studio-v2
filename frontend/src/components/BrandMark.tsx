import { cn } from '@/lib/utils'

/**
 * 应用品牌标识，与 public/favicon.svg 同一套图形。
 * 自带底色与圆角，调用方只需给尺寸（size-7 之类）。
 */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      role="img"
      aria-label="LuxUmbra Slides"
      className={cn('shrink-0', className)}
    >
      <rect width="32" height="32" rx="7" fill="#171614" />
      <rect x="9.5" y="7" width="16" height="10" rx="1.4" fill="#2a2825" />
      <rect
        x="9.5"
        y="7"
        width="16"
        height="10"
        rx="1.4"
        stroke="#3a3732"
        strokeWidth="0.6"
      />
      <rect x="5.5" y="10.5" width="18.5" height="11.5" rx="1.5" fill="#fbfaf6" />
      <rect x="5.5" y="10.5" width="6" height="11.5" rx="1.5" fill="#c8442a" />
      <rect x="13.5" y="14" width="8" height="1.5" rx="0.75" fill="#8a8478" />
      <rect x="13.5" y="17.5" width="5.5" height="1.5" rx="0.75" fill="#b5aea0" />
      <path
        fill="#fbfaf6"
        d="M25.2 6.2l.55 1.55 1.55.55-1.55.55-.55 1.55-.55-1.55-1.55-.55 1.55-.55z"
      />
      <path
        fill="#cfc9bc"
        d="M28.1 9.4l.28.78.78.28-.78.28-.28.78-.28-.78-.78-.28.78-.28z"
      />
    </svg>
  )
}
