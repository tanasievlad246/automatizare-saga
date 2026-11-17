import { Fragment } from 'react'
import { cn } from '@/lib/utils'
import { formatPercent } from '../../format'
import type { TrialJev } from '../../types'
import { spentOnJev } from './describeLine'
import { jevOdds } from './jevOdds'
import { jevSent } from './jevSent'

/**
 * Everything Jev answered about one line (or the whole trial invoice), folded under the line:
 * how likely it found each account, what that cost, and, folded once more, exactly what it
 * was sent. Jev writes no reasons; these figures are what it says.
 */
export function JevSaid({ jev, accounts, open, wholeInvoice }: {
  jev: TrialJev
  accounts: Record<string, string>
  open: boolean
  wholeInvoice: boolean
}) {
  const odds = jevOdds(jev.probabilities, accounts, jev.choice)
  const sent = jevSent(jev.sent, Object.keys(accounts).length)
  const spent = spentOnJev(jev)
  const Heading = wholeInvoice ? 'h4' : 'h3'
  return (
    <details open={open} className="group border-t pt-1">
      <summary className="flex min-h-11 cursor-pointer items-center font-semibold text-primary underline underline-offset-2">
        Ce a spus Jev
      </summary>
      <div className="flex flex-col gap-2.5 pb-1">
        {odds.rows.length > 0 && (
          <>
            {/* Under "Rezultatul" (h2), and for one account per invoice under "Linia după care s-a hotărât" (h3). */}
            <Heading className="text-[1.05rem] font-semibold">Cât de potrivit i se pare fiecare cont</Heading>
            <ul className="flex flex-col gap-1.5">
              {odds.rows.map((row) => (
                // On a narrow screen the account and what it is for take a line of their own, above the bar.
                <li key={row.key} className="grid grid-cols-[minmax(0,1fr)_3rem] items-center gap-x-2.5 gap-y-1 text-[0.95rem] sm:grid-cols-[minmax(0,1fr)_minmax(3rem,7rem)_3rem]">
                  <span className="col-span-2 min-w-0 break-words sm:col-span-1">
                    <span className={cn(!row.none && 'font-bold')}>{row.label}</span>
                    {row.description && <span className="text-muted-foreground"> · {row.description}</span>}
                    {row.chosen && <span className="sr-only"> (ales de Jev)</span>}
                  </span>
                  <span aria-hidden className="h-2.5 overflow-hidden rounded-full bg-muted">
                    <span
                      className={cn('block h-full rounded-full', row.none ? 'bg-attention-foreground/60' : row.chosen ? 'bg-primary' : 'bg-muted-foreground/50')}
                      style={{ width: `${Math.max(2, Math.round(row.share * 100))}%` }}
                    />
                  </span>
                  <span className="text-right font-semibold tabular-nums">{formatPercent(row.share)}</span>
                </li>
              ))}
            </ul>
            {odds.below && <p className="text-[0.9rem] text-muted-foreground">{odds.below}</p>}
            <p className="text-[0.9rem] text-muted-foreground">
              Jev nu scrie motive. Arată doar cât de potrivit i se pare fiecare cont din lista dumneavoastră, după descrierea contului.
              {jev.confidence !== null && ` Cât de sigur este (${formatPercent(jev.confidence)}) este o cifră separată, pe care programul o compară cu pragul.`}
            </p>
          </>
        )}
        {odds.rows.length === 0 && !jev.refused && (
          <p className="text-[0.9rem] text-muted-foreground">Jev nu a spus cât de potrivit i se pare fiecare cont.</p>
        )}
        {spent && <p className="text-[0.9rem] text-muted-foreground">{spent}</p>}
        <details className="rounded-lg">
          <summary className="flex min-h-11 cursor-pointer items-center font-semibold text-primary underline underline-offset-2">
            Ce i s-a trimis lui Jev
          </summary>
          <dl className="grid gap-x-3 gap-y-1.5 rounded-lg bg-muted/60 px-3.5 py-3 text-[0.95rem] sm:grid-cols-[8.5rem_minmax(0,1fr)]">
            {sent.map((row) => (
              <Fragment key={row.label}>
                <dt className="font-semibold">{row.label}</dt>
                <dd className="mb-1.5 [overflow-wrap:anywhere] sm:mb-0">{row.value}</dd>
              </Fragment>
            ))}
          </dl>
          <p className="mt-2 text-[0.9rem] text-muted-foreground">
            Altceva nu pleacă: nici clientul{wholeInvoice ? '' : ', nici celelalte linii'}, nici adrese sau conturi bancare.
          </p>
        </details>
      </div>
    </details>
  )
}
