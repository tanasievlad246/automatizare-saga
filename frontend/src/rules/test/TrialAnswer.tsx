import { TriangleAlert } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { RuleTestResult, TrialAsk } from '../../types'
import { describeAnswer } from './describeAnswer'

const TONES = {
  done: 'border-done-foreground/30 bg-done text-done-foreground',
  attention: 'border-attention-border bg-attention text-attention-foreground',
}

/** What the program said about the trial invoice, in the order the person needs it. */
export function TrialAnswer({ result, ask }: { result: RuleTestResult; ask: TrialAsk }) {
  const said = describeAnswer(result, ask)
  return (
    <section aria-label="Rezultatul" role="status" className="flex flex-col gap-3.5 rounded-2xl border bg-card px-6 py-5.5">
      <h2 className="text-2xl">Rezultatul</h2>
      <div className={cn('rounded-xl border px-4 py-3', TONES[said.tone])}>
        <div className="flex items-center gap-2.5 font-heading text-3xl font-bold">
          {said.tone === 'attention' && said.title.startsWith('Jev nu a putut') && <TriangleAlert aria-hidden className="size-6 shrink-0" />}
          {said.title}
        </div>
        {said.subtitle && <div className="text-lg font-semibold">{said.subtitle}</div>}
      </div>
      {said.label && (
        <p>
          <span className="rounded-full bg-secondary px-3 py-1 font-bold text-secondary-foreground">{said.label}</span>{' '}
          {said.sentences[0]}
        </p>
      )}
      {said.sentences.slice(said.label ? 1 : 0).map((sentence) => <p key={sentence}>{sentence}</p>)}
      {said.technical && (
        <details className="text-[0.9rem] text-muted-foreground">
          <summary className="cursor-pointer font-semibold">Detalii tehnice</summary>
          <p className="mt-1 [overflow-wrap:anywhere]">{said.technical}</p>
        </details>
      )}
    </section>
  )
}
