import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router'
import { Notice } from '@/components/Notice'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api } from '../api'
import { errorMessage, showError } from '../errorMessages'
import { formatDate, formatMoney } from '../format'
import type { Invoice } from '../types'
import { issuedSummary } from './issuedInvoices'

/**
 * The invoices a client issued itself: how many there are, and the list once the switch is
 * turned. The switch is one for all clients and stays as it was left.
 */
export function IssuedInvoicesCard({ cui }: { cui: string }) {
  const queryClient = useQueryClient()
  const settings = useQuery({ queryKey: ['saga-folder'], queryFn: api.sagaFolder })
  const issued = useQuery({ queryKey: ['invoices', cui, 'issued'], queryFn: () => api.issuedInvoices(cui) })
  const turn = useMutation({
    mutationFn: api.showIssued,
    onSuccess: (saved) => queryClient.setQueryData(['saga-folder'], saved),
    onError: showError,
  })
  // While the answer is on its way the switch already stands where it was turned to.
  const shown = turn.isPending ? turn.variables : settings.data?.show_issued === true
  const invoices = issued.data?.invoices ?? []

  return (
    <section aria-labelledby="issued-invoices" className="flex flex-col gap-3.5 rounded-2xl border bg-card px-5 py-4.5">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <div className="min-w-0 flex-[1_1_420px]">
          <h2 id="issued-invoices" className="font-sans text-lg font-bold">Facturile emise de client</h2>
          {issued.data && <p className="text-muted-foreground">{issuedSummary(invoices.length)}</p>}
        </div>
        <label className="flex min-h-12 items-center gap-3 font-semibold">
          <Switch
            checked={shown}
            disabled={!settings.data}
            aria-busy={turn.isPending}
            // Not disabled while the request is on its way: a disabled switch drops the keyboard focus.
            onCheckedChange={(wanted) => {
              if (!turn.isPending) turn.mutate(wanted)
            }}
          />
          Arată facturile emise
        </label>
      </div>
      {issued.error && <Notice tone="attention">{errorMessage(issued.error)}</Notice>}
      {shown && invoices.length > 0 && <IssuedInvoicesTable invoices={invoices} />}
    </section>
  )
}

function IssuedInvoicesTable({ invoices }: { invoices: Invoice[] }) {
  return (
    <div className="overflow-hidden rounded-xl border">
      <Table className="min-w-[640px]">
        <TableHeader>
          <TableRow>
            <TableHead>Cumpărător</TableHead>
            <TableHead>Factura</TableHead>
            <TableHead>Data</TableHead>
            <TableHead className="text-right">Total</TableHead>
            <TableHead><span className="sr-only">Acțiune</span></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {invoices.map((invoice) => (
            <TableRow key={invoice.id}>
              <TableCell className="font-semibold">
                <Link to={`/clienti/${invoice.cui}/facturi/${invoice.id}`} className="text-foreground">
                  {invoice.customer_name}
                </Link>
              </TableCell>
              <TableCell>{invoice.invoice_number}</TableCell>
              <TableCell className="whitespace-nowrap">{formatDate(invoice.invoice_issue_date)}</TableCell>
              <TableCell className="text-right whitespace-nowrap">
                {formatMoney(invoice.total_payable, invoice.currency)}
              </TableCell>
              <TableCell className="text-right">
                <Button asChild size="sm" variant="outline">
                  <Link
                    to={`/clienti/${invoice.cui}/facturi/${invoice.id}`}
                    aria-label={`Deschide factura emisă ${invoice.invoice_number ?? ''} către ${invoice.customer_name ?? ''}`}
                  >
                    Deschide
                  </Link>
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
