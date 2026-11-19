import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Notice } from '@/components/Notice'
import { Button } from '@/components/ui/button'
import { api } from '../../api'
import { errorMessage } from '../../errorMessages'
import { formatWhen } from '../../format'
import { JevOdds } from '../../rules/JevOdds'
import { EMPTY_HISTORY, FOLD_AFTER, JEV_ODDS, type HistoryRow, type Moment, moments, rowLabel, showAllLabel } from './decisionTexts'

/**
 * The tab "Cum s-a ales contul": each change of the invoice's account, the newest first, with the
 * lines it changed, why, and what they had before. `names`: each line's name, by number;
 * `accounts`: those of the invoice's kind, for what Jev said of each.
 */
export function DecisionHistory({ invoiceId, names, accounts }: {
  invoiceId: string
  names: Record<number, string>
  accounts: Record<string, string>
}) {
  const { data, error } = useQuery({ queryKey: ['decisions', invoiceId], queryFn: () => api.decisions(invoiceId) })
  if (error) return <div className="px-6 py-6"><Notice tone="attention">{errorMessage(error)}</Notice></div>
  if (!data) return <p role="status" className="px-6 py-6 text-muted-foreground">Se încarcă istoricul…</p>
  const found = moments(data.decisions)
  if (found.length === 0) return <p className="px-6 py-6 text-muted-foreground">{EMPTY_HISTORY}</p>
  return (
    <ol className="flex flex-col divide-y px-6 pt-1.5 pb-4">
      {found.map((moment) => <MomentItem key={moment.key} moment={moment} names={names} accounts={accounts} />)}
    </ol>
  )
}

function MomentItem({ moment, names, accounts }: { moment: Moment; names: Record<number, string>; accounts: Record<string, string> }) {
  const [all, setAll] = useState(false)
  const when = formatWhen(moment.at)
  const shown = all ? moment.rows : moment.rows.slice(0, FOLD_AFTER)
  return (
    <li className="flex flex-col gap-2.5 py-4">
      <p>
        <span className="text-lg font-bold">{when.charAt(0).toUpperCase() + when.slice(1)}</span>
        <span className="font-semibold text-muted-foreground"> · {moment.label}</span>
      </p>
      <ul className="flex flex-col gap-2">
        {shown.map((row) => <RowItem key={row.key} row={row} names={names} accounts={accounts} />)}
      </ul>
      {moment.rows.length > FOLD_AFTER && !all && (
        <Button variant="link" className="self-start px-0" onClick={() => setAll(true)}>{showAllLabel(moment.lineCount)}</Button>
      )}
    </li>
  )
}

function RowItem({ row, names, accounts }: { row: HistoryRow; names: Record<number, string>; accounts: Record<string, string> }) {
  return (
    <li className="grid gap-x-4 gap-y-1 rounded-xl bg-background px-3.5 py-2.5 sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)]">
      <div className="font-semibold [overflow-wrap:anywhere]">{rowLabel(row.lines, names)}</div>
      <div className="min-w-0">
        <p>
          {row.cont
            ? <span className="font-heading text-xl font-bold">{row.cont}</span>
            : <span className="font-bold text-attention-foreground">de verificat</span>}
          {' · '}{row.text}
          {row.before && <span className="text-[0.9rem] text-muted-foreground"> · {row.before}</span>}
        </p>
        {row.odds && (
          <details className="mt-1">
            <summary className="flex min-h-10 cursor-pointer items-center font-semibold text-primary underline underline-offset-2">
              {JEV_ODDS}
            </summary>
            <div className="flex flex-col gap-2 pt-1">
              <JevOdds probabilities={row.odds.probabilities} accounts={accounts} choice={row.odds.choice} />
              <p className="text-[0.9rem] text-muted-foreground">
                Jev nu scrie motive. Arată doar cât de potrivit i se pare fiecare cont din lista dumneavoastră.
              </p>
            </div>
          </details>
        )}
      </div>
    </li>
  )
}
