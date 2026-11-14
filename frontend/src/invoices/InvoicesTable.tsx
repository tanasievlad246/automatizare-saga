import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { formatDate, formatMoney } from '../format'
import type { Invoice } from '../types'
import { InvoiceStateBadges } from './InvoiceStateBadges'
import { needsAnAccount } from './invoiceState'

/** A client's invoices, one per row, each leading to the invoice itself. */
export function InvoicesTable({ invoices }: { invoices: Invoice[] }) {
  if (invoices.length === 0) {
    return <p className="rounded-2xl border bg-card px-6 py-8 text-lg">Nicio factură aici.</p>
  }
  return (
    <div className="overflow-hidden rounded-2xl border bg-card">
      <Table className="min-w-[820px]">
        <TableHeader>
          <TableRow>
            <TableHead>Furnizor</TableHead>
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
                <TableCell className="font-semibold">{invoice.supplier_name}</TableCell>
                <TableCell>{invoice.invoice_number}</TableCell>
                <TableCell className="whitespace-nowrap">{formatDate(invoice.invoice_issue_date)}</TableCell>
                <TableCell className="text-right whitespace-nowrap">
                  {formatMoney(invoice.total_payable, invoice.currency)}
                </TableCell>
                <TableCell>
                  {invoice.cont ? (
                    <span className="font-heading text-xl font-bold">{invoice.cont}</span>
                  ) : (
                    <span className="text-muted-foreground">neales</span>
                  )}
                </TableCell>
                <TableCell><InvoiceStateBadges invoice={invoice} /></TableCell>
                <TableCell className="text-right">
                  <Button
                    asChild
                    size="sm"
                    variant={waiting ? 'default' : 'outline'}
                    className={cn(waiting && 'bg-attention-foreground hover:bg-attention-foreground/85')}
                  >
                    <Link to={`/clienti/${invoice.cui}/facturi/${invoice.id}`}>
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
