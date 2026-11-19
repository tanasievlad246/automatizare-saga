import { cn } from '@/lib/utils'
import { formatPercent } from '../format'
import { jevOdds } from './test/jevOdds'

/**
 * How likely Jev found each account it was offered, as bars from the most likely, and the
 * accounts it found unlikely in one sentence. Jev writes no reasons: these figures are what it says.
 */
export function JevOdds({ probabilities, accounts, choice }: {
  probabilities: Record<string, number>
  accounts: Record<string, string>
  choice: string | null
}) {
  const odds = jevOdds(probabilities, accounts, choice)
  return (
    <>
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
    </>
  )
}
