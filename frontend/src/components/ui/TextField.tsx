import { type InputHTMLAttributes, useId } from 'react'
import { cn } from '@/lib/utils'

interface TextFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  hint?: string
}

export function TextField({ label, hint, className, id, ...props }: TextFieldProps) {
  const generatedId = useId()
  const inputId = id ?? generatedId
  const hintId = hint ? `${inputId}-hint` : undefined

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={inputId} className="text-[13px] font-medium text-ink-soft">
        {label}
      </label>
      <input
        {...props}
        id={inputId}
        aria-describedby={hintId}
        className={cn(
          'h-11 rounded-xl border border-line bg-surface px-3.5 text-[15px] text-ink',
          'placeholder:text-ink-muted/70 focus:border-accent focus:outline-none',
          'transition-colors duration-150 disabled:bg-surface-soft disabled:text-ink-muted',
          className,
        )}
      />
      {hint && (
        <span id={hintId} className="text-xs text-ink-muted">
          {hint}
        </span>
      )}
    </div>
  )
}
