import { Loader2, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/Button'

export function EmptyStage({ pending, onGenerate }: { pending: boolean; onGenerate: () => void }) {
  return (
    <main className="bg-stage grid flex-1 place-items-center p-8">
      <div className="max-w-sm rounded-3xl border border-line bg-surface px-8 py-10 text-center shadow-card">
        <Sparkles className="mx-auto mb-3 size-5 text-accent" />
        <p className="text-sm font-medium">大纲已确认，还没有生成页面</p>
        <p className="mt-1.5 text-[13px] leading-relaxed text-ink-muted">
          生成过程中就能编辑，完成一页显示一页。
        </p>
        <Button className="mt-5" disabled={pending} onClick={onGenerate}>
          {pending ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
          生成 PPT
        </Button>
      </div>
    </main>
  )
}
