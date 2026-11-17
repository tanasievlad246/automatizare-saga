import { TriangleAlert } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { RuleTestResult, TrialAsk } from '../../types'
import { describeTrial } from './describeTrial'
import { TrialLineCard } from './TrialLineCard'

const TONES = {
  done: 'border-done-foreground/30 bg-done text-done-foreground',
  attention: 'border-attention-border bg-attention text-attention-foreground',
}

/**
 * What the program said about the trial invoice: first whether it would get its accounts by
 * itself, then each line with its account and why. With one account per invoice, the line
 * it was decided by, when there is something to say about it.
 */
export function TrialAnswer({ result, ask, linesOnInvoice, clientName, currency }: {
  result: RuleTestResult
  ask: TrialAsk
  linesOnInvoice: number
  clientName?: string
  currency: string
}) {
  const said = describeTrial(result, linesOnInvoice, ask)
  const wholeInvoice = !result.per_line
  const lines = wholeInvoice && said.failed ? [] : result.lines
  return (
    <section aria-label="Rezultatul" role="status" className="flex flex-col gap-3.5 rounded-2xl border bg-card px-6 py-5.5">
      <h2 className="text-2xl">Rezultatul</h2>
      <div className={cn('rounded-xl border px-4 py-3', TONES[said.tone])}>
        <div className="flex items-center gap-2.5 font-heading text-3xl font-bold">
          {said.failed && <TriangleAlert aria-hidden className="size-6 shrink-0" />}
          {said.title}
        </div>
        {said.subtitle && <div className="text-lg font-semibold">{said.subtitle}</div>}
      </div>
      {said.sentences.map((sentence) => <p key={sentence}>{sentence}</p>)}
      {said.technical && (
        <details className="text-[0.9rem] text-muted-foreground">
          <summary className="cursor-pointer font-semibold">Detalii tehnice</summary>
          <p className="mt-1 [overflow-wrap:anywhere]">{said.technical}</p>
        </details>
      )}
      {lines.length > 0 && (
        <>
          {wholeInvoice && <h3 className="text-lg font-semibold">{linesOnInvoice > 1 ? 'Linia după care s-a hotărât' : 'Linia facturii'}</h3>}
          <ol aria-label="Liniile facturii" className="flex flex-col gap-3">
            {lines.map((entry) => (
              <TrialLineCard
                key={entry.line}
                entry={entry}
                context={{ ask, clientName, wholeInvoice, stoppedAt: result.jev_stopped?.line }}
                accounts={result.accounts}
                currency={currency}
                // With one question asked, what Jev said is shown at once; with several, each opens on its own.
                jevOpen={result.jev_calls === 1}
              />
            ))}
          </ol>
        </>
      )}
    </section>
  )
}
