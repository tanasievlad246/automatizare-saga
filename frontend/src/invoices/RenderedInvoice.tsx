import { Fragment } from 'react'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { formatAmount, formatDate, formatNumber } from '../format'
import type { InvoiceDocument, LineAccount, Party } from '../types'
import { totalRows, totalsNote } from './invoiceTotals'
import { ON_WHOLE_INVOICE, whoChoseLine } from './lineAccounts'

/**
 * The account of each row, for an invoice decided line by line: its lines, and each discount or
 * charge on the whole invoice. `onChoose` is null once it is imported.
 */
export type LineColumn = {
  accounts: LineAccount[]
  onChoose: ((line: number) => void) | null
}

const ROW_WEIGHTS = { plain: '', bold: 'font-bold', large: 'text-xl font-bold' }

/**
 * The invoice as a person reads it: who, when, what was bought, how much. `goesToSaga` is
 * false for an invoice the client issued, which is only looked at. With `lineColumn`, each
 * line shows its account and can be given another; the price then makes room for it.
 */
export function RenderedInvoice({
  document, goesToSaga, lineColumn = null,
}: { document: InvoiceDocument; goesToSaga: boolean; lineColumn?: LineColumn | null }) {
  const accountOf = new Map(lineColumn?.accounts.map((entry) => [entry.line, entry]))
  const note = totalsNote(document, goesToSaga)
  // SAGA has no credit notes; they are booked as invoices with negative amounts, so say what this is.
  const kind = document.is_credit_note ? 'Factură de stornare (scade din ce datorează clientul)' : null
  return (
    <div className="flex flex-col gap-5 px-6 pt-5.5 pb-6.5">
      {kind && <p className="font-semibold text-attention-foreground">{kind}</p>}
      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(240px,100%),1fr))] gap-5">
        <PartyBlock role="Furnizor" party={document.supplier} />
        <PartyBlock role="Cumpărător" party={document.customer} />
      </div>
      <dl className="grid grid-cols-[repeat(auto-fit,minmax(min(150px,100%),1fr))] gap-x-5 gap-y-3 rounded-xl bg-background px-4 py-3.5">
        <Fact name="Număr" value={document.number} />
        <Fact name="Data" value={formatDate(document.issue_date)} />
        <Fact name="Scadență" value={formatDate(document.due_date) || 'nu este scrisă'} />
      </dl>
      <Table className="min-w-[520px]">
        <TableHeader>
          <TableRow>
            <TableHead>Denumire</TableHead>
            <TableHead className="text-right">Cantitate</TableHead>
            {!lineColumn && <TableHead className="text-right">Preț</TableHead>}
            <TableHead className="text-right">Valoare</TableHead>
            <TableHead className="text-right">TVA</TableHead>
            {lineColumn && <TableHead>Cont</TableHead>}
          </TableRow>
        </TableHeader>
        <TableBody>
          {document.lines.map((line) => {
            const entry = accountOf.get(line.number)
            const waiting = lineColumn !== null && !entry?.cont
            return (
              <TableRow key={line.number} className={cn(waiting && 'bg-attention/40 hover:bg-attention/50')}>
                <TableCell className="font-semibold">
                  {line.description}
                  {/* The item's description, when it says more than its name. */}
                  {line.details && <div className="mt-0.5 text-[0.9rem] font-normal text-muted-foreground">{line.details}</div>}
                </TableCell>
                <TableCell className="text-right whitespace-nowrap">
                  {formatNumber(line.quantity)} {line.unit_name?.toLowerCase()}
                </TableCell>
                {!lineColumn && <TableCell className="text-right">{formatAmount(line.unit_price)}</TableCell>}
                <TableCell className="text-right">{formatAmount(line.value)}</TableCell>
                <TableCell className="text-right">{line.vat_percent ? `${formatNumber(line.vat_percent)}%` : ''}</TableCell>
                {lineColumn && (
                  <AccountCell entry={entry} number={line.number} description={line.description} onChoose={lineColumn.onChoose} />
                )}
              </TableRow>
            )
          })}
          {/* A discount or a charge on the whole invoice: a row after the lines, with its own account. */}
          {document.adjustments.map((adjustment) => {
            const entry = accountOf.get(adjustment.number)
            const waiting = lineColumn !== null && !entry?.cont
            return (
              <TableRow key={adjustment.number} className={cn(waiting && 'bg-attention/40 hover:bg-attention/50')}>
                <TableCell className="font-semibold">
                  {adjustment.description}
                  <div className="mt-0.5 text-[0.9rem] font-normal text-muted-foreground">{ON_WHOLE_INVOICE}</div>
                </TableCell>
                <TableCell colSpan={lineColumn ? 1 : 2} />
                <TableCell className="text-right">
                  {adjustment.is_charge ? '' : '−'}{formatAmount(adjustment.amount)}
                </TableCell>
                <TableCell className="text-right">{adjustment.vat_percent ? `${formatNumber(adjustment.vat_percent)}%` : ''}</TableCell>
                {lineColumn && (
                  <AccountCell entry={entry} number={adjustment.number} description={adjustment.description} onChoose={lineColumn.onChoose} />
                )}
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
      <dl className="grid grid-cols-[auto_auto] gap-x-7 gap-y-1.5 self-end text-right">
        {totalRows(document).map((row) => (
          <Fragment key={row.label}>
            <dt className={row.weight === 'plain' ? 'text-muted-foreground' : ROW_WEIGHTS[row.weight]}>{row.label}</dt>
            <dd className={ROW_WEIGHTS[row.weight]}>{row.amount}</dd>
          </Fragment>
        ))}
      </dl>
      {note && <p className="rounded-xl bg-fresh px-4 py-3 text-fresh-foreground">{note}</p>}
    </div>
  )
}

/**
 * A row's account, who chose it and the button, in one cell: a column more would push the
 * button out of sight beside the account card.
 */
function AccountCell({
  entry, number, description, onChoose,
}: { entry: LineAccount | undefined; number: number; description: string; onChoose: ((line: number) => void) | null }) {
  const waiting = !entry?.cont
  return (
    <TableCell className="w-44 whitespace-normal">
      <div className="flex flex-col items-start gap-1">
        {entry?.cont ? (
          <span className="font-heading text-xl leading-tight font-bold">{entry.cont}</span>
        ) : (
          <span className="font-bold text-attention-foreground">fără cont</span>
        )}
        {entry && <span className="text-[0.85rem] leading-snug text-muted-foreground">{whoChoseLine(entry)}</span>}
        {entry && onChoose && (
          <Button
            size="sm"
            variant={waiting ? 'default' : 'outline'}
            className={cn('mt-0.5', waiting && 'bg-attention-foreground hover:bg-attention-foreground/85')}
            aria-label={`${waiting ? 'Alege contul' : 'Schimbă contul'} pentru linia ${number}: ${description}`}
            onClick={() => onChoose(number)}
          >
            {waiting ? 'Alege contul' : 'Schimbă'}
          </Button>
        )}
      </div>
    </TableCell>
  )
}

function PartyBlock({ role, party }: { role: string; party: Party }) {
  return (
    <div>
      <div className="text-[0.9rem] font-semibold text-muted-foreground">{role}</div>
      <div className="text-xl font-bold">{party.name}</div>
      <div>CUI {party.vat_id ?? party.cui}</div>
      <div>{[party.address, party.city].filter(Boolean).join(', ')}</div>
    </div>
  )
}

function Fact({ name, value }: { name: string; value: string | null }) {
  return (
    <div>
      <dt className="text-[0.9rem] text-muted-foreground">{name}</dt>
      <dd className="font-semibold">{value}</dd>
    </div>
  )
}
