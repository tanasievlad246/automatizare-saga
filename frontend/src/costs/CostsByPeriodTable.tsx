import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatPeriod, formatUsd, formatUsdExact } from '../format'
import type { Costs } from '../types'

/** The cost of each day, week, month or year in the chosen range, newest first. */
export function CostsByPeriodTable({ periods }: { periods: Costs['by_period'] }) {
  if (periods.length === 0) {
    return <p className="rounded-2xl border bg-card px-6 py-6 text-lg">Jev nu a fost întrebat nimic în această perioadă.</p>
  }
  return (
    <div className="overflow-hidden rounded-2xl border bg-card">
      <Table className="min-w-[420px]">
        <TableHeader>
          <TableRow>
            <TableHead>Perioada</TableHead>
            <TableHead className="text-right">Facturi clasificate</TableHead>
            <TableHead className="text-right">Cost</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {[...periods].reverse().map((period) => (
            <TableRow key={period.period}>
              <TableCell className="font-semibold">{formatPeriod(period.period)}</TableCell>
              <TableCell className="text-right">{period.invoices.toLocaleString('ro-RO')}</TableCell>
              <TableCell className="text-right font-semibold whitespace-nowrap" title={formatUsdExact(period.cost_usd)}>{formatUsd(period.cost_usd)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
