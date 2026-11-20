import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'
import { Notice } from '@/components/Notice'
import { Pager } from '@/components/Pager'
import { pageOf, rangeLine } from '@/components/paging'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api } from '../api'
import { errorMessage } from '../errorMessages'
import { countOf, formatAmount, formatNumber } from '../format'
import { isIssued } from '../invoices/issuedInvoices'
import { LineAccountDialog } from '../invoices/LineAccountDialog'
import { lineTarget, whoChoseInvoice, whoChoseLine } from '../invoices/lineAccounts'
import { InvoiceAccountDialog } from './InvoiceAccountDialog'
import { FILES_TAB, LINES_PER_PAGE, lineRows } from './waitingFiles'

const LINE_NOUN = { one: 'Linia', many: 'Liniile' }

/**
 * Under an open invoice of a file: its lines as SAGA gets them, a page at a time, each with its
 * account. An account is changed from here: line by line where the invoice has one on each line,
 * once for the whole invoice where it has one for all.
 */
export function InvoiceLines({ invoiceId, cui, number }: { invoiceId: string; cui: string; number: string }) {
  // The same answer the invoice's own screen reads, so a change made on either is seen on both.
  const { data: view, error } = useQuery({ queryKey: ['invoice', invoiceId], queryFn: () => api.invoiceView(invoiceId) })
  const rules = useQuery({ queryKey: ['rules'], queryFn: api.rules }).data
  const [wanted, setWanted] = useState(1)
  const [choosing, setChoosing] = useState<number | 'all' | 'invoice' | null>(null)

  if (error) return <div className="px-4 py-4"><Notice tone="attention">{errorMessage(error)}</Notice></div>
  if (!view) return <p role="status" className="px-4 py-4 text-muted-foreground">Se încarcă liniile facturii…</p>
  const { invoice, document } = view
  if (!document) {
    return <p className="px-4 py-4 text-muted-foreground">Fișierul de la ANAF al acestei facturi nu se poate citi, așa că liniile ei nu se pot arăta.</p>
  }
  const perLine = invoice.line_accounts
  // Only the accounts of the invoice's own kind can be chosen.
  const accounts = (isIssued(invoice) ? rules?.issued_accounts : rules?.accounts) ?? {}
  const page = pageOf(lineRows(document, perLine, invoice.cont), wanted, LINES_PER_PAGE)
  // An imported invoice is in no file; should one be shown all the same, its account stays.
  const editable = !invoice.uploaded_to_accounting
  const target = choosing === 'invoice' ? null : lineTarget(document, perLine, choosing)
  const who = whoChoseInvoice(invoice)

  return (
    <div className="flex flex-col gap-3 bg-background px-4 py-4 @3xl:pl-16">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <p className="min-w-0 flex-[1_1_280px]">
          <strong>Liniile facturii {number}</strong>
          <span className="text-muted-foreground"> · {countOf(document.lines.length, 'o linie', 'linii')} · </span>
          <Link to={`/clienti/${cui}/facturi/${invoiceId}`} className="font-semibold">Deschide factura</Link>
        </p>
        {perLine && editable && (
          <Button variant="outline" size="sm" onClick={() => setChoosing('all')}>Același cont pe toate liniile</Button>
        )}
      </div>
      {!perLine && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border bg-card px-4 py-3">
          <p className="min-w-0 flex-[1_1_260px]">
            {FILES_TAB.oneAccount} <strong className="font-heading text-xl">{invoice.cont ?? '—'}</strong>
            {who && <span className="text-muted-foreground"> · {who}</span>}
          </p>
          {editable && (
            <Button variant="outline" size="sm" aria-label={`Schimbă contul facturii ${number}`} onClick={() => setChoosing('invoice')}>
              Schimbă contul
            </Button>
          )}
        </div>
      )}
      <div className="overflow-hidden rounded-xl border bg-card">
        <Table className="min-w-[560px]">
          <TableHeader>
            <TableRow>
              <TableHead className="w-12">Nr.</TableHead>
              <TableHead>Denumire</TableHead>
              <TableHead className="text-right">Cantitate</TableHead>
              <TableHead className="text-right">Valoare</TableHead>
              <TableHead className="text-right">TVA</TableHead>
              {perLine && <TableHead>Cont</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {page.items.map((row, index) => (
              <TableRow key={row.number ?? `adjustment-${index}`}>
                <TableCell className="text-muted-foreground">{row.number ?? ''}</TableCell>
                <TableCell className="font-semibold whitespace-normal">
                  {row.description}
                  {/* The item's description, when it says more than its name. */}
                  {row.details && <div className="mt-0.5 text-[0.9rem] font-normal text-muted-foreground">{row.details}</div>}
                </TableCell>
                <TableCell className="text-right whitespace-nowrap">
                  {row.quantity !== null && `${formatNumber(row.quantity)} ${row.unit_name?.toLowerCase() ?? ''}`}
                </TableCell>
                <TableCell className="text-right whitespace-nowrap tabular-nums">{formatAmount(row.value)}</TableCell>
                <TableCell className="text-right whitespace-nowrap">{row.vat_percent ? `${formatNumber(row.vat_percent)}%` : ''}</TableCell>
                {perLine && (
                  <TableCell className="whitespace-normal">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                      <div className="min-w-0 flex-[1_1_9rem]">
                        <span className="font-heading text-lg leading-tight font-bold">{row.cont ?? 'fără cont'}</span>
                        <span className="block text-[0.85rem] leading-snug text-muted-foreground">
                          {row.entry ? whoChoseLine(row.entry) : 'contul facturii'}
                        </span>
                      </div>
                      {row.entry && row.number !== null && editable && (
                        <Button
                          variant="outline" size="sm"
                          aria-label={`Schimbă contul pentru linia ${row.number}: ${row.description}`}
                          onClick={() => setChoosing(row.number)}
                        >
                          Schimbă
                        </Button>
                      )}
                    </div>
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <Pager page={page} label={`Paginile liniilor facturii ${number}`} line={rangeLine(page, LINE_NOUN)} onPage={setWanted} />
      {editable && <p className="text-[0.9rem] text-muted-foreground">{FILES_TAB.afterAChange}</p>}

      {target && (
        <LineAccountDialog
          key={String(choosing)} invoice={invoice} target={target} accounts={accounts}
          jevReady={rules?.jev_configured ?? false} canDecideAgain={false} onClose={() => setChoosing(null)}
        />
      )}
      {choosing === 'invoice' && (
        <InvoiceAccountDialog
          invoice={invoice} accounts={accounts} likelihoods={view.jev?.probabilities ?? null} onClose={() => setChoosing(null)}
        />
      )}
    </div>
  )
}
