import { cn } from '@/lib/utils'
import { formatMoney } from '../../format'
import type { TrialLineAnswer } from '../../types'
import { describeLine } from './describeLine'
import type { LineContext, LineSaid } from './describeLine'
import { JevSaid } from './JevSaid'

const CHIPS: Record<NonNullable<LineSaid['chip']>['kind'], string> = {
  rule: 'bg-done text-done-foreground',
  jev: 'bg-secondary text-secondary-foreground',
  follows: 'bg-muted text-foreground',
  waiting: 'border border-attention-border bg-attention text-attention-foreground',
}

/** One line of the trial invoice: what it is, the account it gets, who gave it, and why. */
export function TrialLineCard({ entry, context, accounts, currency, jevOpen }: {
  entry: TrialLineAnswer
  context: LineContext
  accounts: Record<string, string>
  currency: string
  jevOpen: boolean
}) {
  const said = describeLine(entry, context)
  const waits = said.tone === 'attention'
  return (
    <li className={cn('flex flex-col gap-2 rounded-xl border bg-card px-4 py-3.5', waits && 'border-2 border-attention-border')}>
      <div className="flex items-start gap-2.5">
        <span aria-hidden className="flex size-7.5 shrink-0 items-center justify-center rounded-full bg-muted text-[0.9rem] font-bold">
          {entry.line}
        </span>
        <span className="min-w-0 pt-0.5 font-semibold [overflow-wrap:anywhere]">
          <span className="sr-only">Linia {entry.line}: </span>{entry.description}
        </span>
        <span className="ml-auto whitespace-nowrap pt-0.5 text-muted-foreground tabular-nums">{formatMoney(entry.value, currency)}</span>
      </div>
      <div className={cn('font-heading text-[1.4rem] font-bold leading-tight', waits && 'text-attention-foreground')}>
        {said.heading}
        {said.headingNote && <span className="font-sans text-base font-medium"> · {said.headingNote}</span>}
      </div>
      <p>
        {said.chip && <span className={cn('mr-1.5 inline-block rounded-full px-2.5 py-0.5 text-[0.9rem] font-bold', CHIPS[said.chip.kind])}>{said.chip.text}</span>}
        {said.sentence}
      </p>
      {said.notes.map((note) => <p key={note} className="text-[0.9rem] text-muted-foreground">{note}</p>)}
      {said.technical && (
        <details className="text-[0.9rem] text-muted-foreground">
          <summary className="cursor-pointer font-semibold">Detalii tehnice</summary>
          <p className="mt-1 [overflow-wrap:anywhere]">{said.technical}</p>
        </details>
      )}
      {said.jevShown && entry.jev && (
        <JevSaid jev={entry.jev} accounts={accounts} open={jevOpen} wholeInvoice={context.wholeInvoice ?? false} />
      )}
    </li>
  )
}
