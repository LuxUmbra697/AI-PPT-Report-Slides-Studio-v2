import type { ButtonHTMLAttributes, Ref } from 'react'
import { cn } from '@/lib/utils'

type Variant = 'primary' | 'accent' | 'ghost' | 'soft'
type Size = 'sm' | 'md' | 'lg'

const VARIANT_STYLE: Record<Variant, string> = {
  primary: 'bg-ink text-white hover:bg-ink/90 disabled:hover:bg-ink',
  accent: 'bg-accent text-white hover:brightness-110 disabled:hover:brightness-100',
  ghost: 'border border-line bg-surface text-ink-soft hover:border-line-strong hover:text-ink',
  soft: 'bg-accent-soft text-accent hover:bg-accent hover:text-white',
}

const SIZE_STYLE: Record<Size, string> = {
  sm: 'h-8 px-3 text-[13px]',
  md: 'h-10 px-4 text-sm',
  lg: 'h-12 px-6 text-[15px]',
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  ref?: Ref<HTMLButtonElement>
}

export function Button({ variant = 'primary', size = 'md', className, ...props }: ButtonProps) {
  return (
    <button
      {...props}
      className={cn(
        'inline-flex items-center justify-center gap-1.5 rounded-full font-medium whitespace-nowrap',
        'transition-all duration-150 active:translate-y-px',
        'disabled:cursor-not-allowed disabled:opacity-45 disabled:active:translate-y-0',
        SIZE_STYLE[size],
        VARIANT_STYLE[variant],
        className,
      )}
    />
  )
}
