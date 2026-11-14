import { Check, TriangleAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

const TONES = {
  attention: 'border-attention-border bg-attention text-attention-foreground',
  done: 'border-transparent bg-done text-done-foreground',
  fresh: 'border-transparent bg-fresh text-fresh-foreground',
}

/** A coloured box that tells the person something. The colour repeats what the words say. */
export function Notice({
  tone, children, className,
}: { tone: keyof typeof TONES; children: ReactNode; className?: string }) {
  const Icon = tone === 'attention' ? TriangleAlert : Check
  return (
    <div className={cn('flex items-start gap-3 rounded-xl border px-4 py-3', TONES[tone], className)}>
      <Icon aria-hidden className="mt-0.5 size-5 shrink-0" />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  )
}
