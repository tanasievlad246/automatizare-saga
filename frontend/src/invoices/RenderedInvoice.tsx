import { Fragment } from 'react'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatAmount, formatDate, formatNumber } from '../format'
import type { InvoiceDocument, Party } from '../types'
import { totalRows, totalsNote } from './invoiceTotals'

const ROW_WEIGHTS = { plain: '', bold: 'font-bold', large: 'text-xl font-bold' }

/**
 * The invoice as a person reads it: who, when, what was bought, how much. `goesToSaga` is
 * false for an invoice the client issued, which is only looked at.
 */
export function RenderedInvoice({ document, goesToSaga }: { document: InvoiceDocument; goesToSaga: boolean }) {
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
            <TableHead className="text-right">Preț</TableHead>
            <TableHead className="text-right">Valoare</TableHead>
            <TableHead className="text-right">TVA</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {document.lines.map((line) => (
            <TableRow key={line.number}>
              <TableCell className="font-semibold">{line.description}</TableCell>
              <TableCell className="text-right whitespace-nowrap">
                {formatNumber(line.quantity)} {line.unit_name?.toLowerCase()}
              </TableCell>
              <TableCell className="text-right">{formatAmount(line.unit_price)}</TableCell>
              <TableCell className="text-right">{formatAmount(line.value)}</TableCell>
              <TableCell className="text-right">{line.vat_percent ? `${formatNumber(line.vat_percent)}%` : ''}</TableCell>
            </TableRow>
          ))}
          {document.adjustments.map((adjustment, index) => (
            <TableRow key={`adjustment-${index}`}>
              <TableCell className="font-semibold">
                {adjustment.reason ?? (adjustment.is_charge ? 'Taxă suplimentară' : 'Reducere')}
              </TableCell>
              <TableCell colSpan={2} />
              <TableCell className="text-right">
                {adjustment.is_charge ? '' : '−'}{formatAmount(adjustment.amount)}
              </TableCell>
              <TableCell />
            </TableRow>
          ))}
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
