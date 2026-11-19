import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { formatDate, formatMoney } from '../format'
import type { Invoice } from '../types'
import type { Party } from './invoiceList'
import { InvoiceStateBadges } from './InvoiceStateBadges'
import { needsAnAccount } from './invoiceState'
import { listAccount } from './lineAccounts'

/**
 * A client's invoices, one per row, each leading to the invoice itself: received ones by their
 * supplier, issued ones by their buyer (`party`). While they are still being read it says so,
 * instead of claiming there are none.
 */
export function InvoicesTable({
  invoices, party = 'supplier', loading, whenEmpty,
}: { invoices: Invoice[]; party?: Party; loading: boolean; whenEmpty: string }) {
  const nameOf = (invoice: Invoice) => (party === 'supplier' ? invoice.supplier_name ?? 'Furnizor necunoscut' : invoice.customer_name ?? 'Client necunoscut')
  if (loading) {
    return <p role="status" className="rounded-2xl border bg-card px-6 py-8 text-lg text-muted-foreground">Se încarcă facturile…</p>
  }
  if (invoices.length === 0) {
    return <p className="rounded-2xl border bg-card px-6 py-8 text-lg">{whenEmpty}</p>
  }
  return (
    <div className="overflow-hidden rounded-2xl border bg-card">
      <Table className="min-w-[820px]">
        <TableHeader>
          <TableRow>
            <TableHead>{party === 'supplier' ? 'Furnizor' : 'Cumpărător'}</TableHead>
            <TableHead>Factura</TableHead>
            <TableHead>Data</TableHead>
            <TableHead className="text-right">Total</TableHead>
            <TableHead>Cont</TableHead>
            <TableHead>Stare</TableHead>
            <TableHead><span className="sr-only">Acțiune</span></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {invoices.map((invoice) => {
            const waiting = needsAnAccount(invoice)
            return (
              <TableRow key={invoice.id} className={cn(waiting && 'bg-attention/40 hover:bg-attention/50')}>
                {/* The name itself opens the invoice, so it can be reached even when the
                    last column is scrolled out of a narrow window. */}
                <TableCell className="font-semibold">
                  <Link to={`/clienti/${invoice.cui}/facturi/${invoice.id}`} className="text-foreground">
                    {nameOf(invoice)}
                  </Link>
                </TableCell>
                <TableCell>{invoice.invoice_number}</TableCell>
                <TableCell className="whitespace-nowrap">{formatDate(invoice.invoice_issue_date)}</TableCell>
                <TableCell className="text-right whitespace-nowrap">
                  {formatMoney(invoice.total_with_vat, invoice.currency)}
                </TableCell>
                <TableCell>
                  <AccountShown invoice={invoice} />
                </TableCell>
                <TableCell><InvoiceStateBadges invoice={invoice} /></TableCell>
                <TableCell className="text-right">
                  <Button
                    asChild
                    size="sm"
                    variant={waiting ? 'default' : 'outline'}
                    className={cn(waiting && 'bg-attention-foreground hover:bg-attention-foreground/85')}
                  >
                    <Link
                      to={`/clienti/${invoice.cui}/facturi/${invoice.id}`}
                      aria-label={`${waiting ? 'Alege contul pentru' : 'Deschide'} factura ${invoice.invoice_number ?? ''} ${party === 'supplier' ? 'de la' : 'către'} ${nameOf(invoice)}`}
                    >
                      {waiting ? 'Alege contul' : 'Deschide'}
                    </Link>
                  </Button>
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}

/** "605", "605 +1" when its lines are on other accounts too, "605 · o linie fără cont" while some wait. */
function AccountShown({ invoice }: { invoice: Invoice }) {
  const { main, more } = listAccount(invoice)
  return (
    <span className="flex flex-wrap items-baseline gap-x-2">
      {main ? <span className="font-heading text-xl font-bold">{main}</span> : !more && <span className="text-muted-foreground">neales</span>}
      {more && <span className="text-[0.9rem] text-muted-foreground">{more}</span>}
    </span>
  )
}
