import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Notice } from '@/components/Notice'
import { Pager } from '@/components/Pager'
import { pageOf, rangeLine } from '@/components/paging'
import { scrollBelowHeader } from '@/components/scrollBelowHeader'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api } from '../api'
import { errorMessage, showError } from '../errorMessages'
import { formatDate, formatMoney } from '../format'
import type { Invoice } from '../types'
import { InvoiceFilters } from './InvoiceFilters'
import {
  INVOICES_PER_PAGE, type ListState, clearFilters, filterInvoices, filtersOn, foundLine, readListState, sortInvoices,
  writeListState,
} from './invoiceList'
import { issuedSummary } from './issuedInvoices'

// The issued list's choices are in the address beside the received list's, each name with this in front.
const ISSUED = 'emise-'

/**
 * The invoices a client issued itself: how many there are (`count`, unknown while the page
 * is still loading), and the list once the switch is turned, found by buyer, number or days,
 * in the order chosen, a page at a time. The switch is one for all clients and stays as it
 * was left. The list is asked for only while it is shown.
 */
export function IssuedInvoicesCard({ cui, count }: { cui: string; count: number | undefined }) {
  const queryClient = useQueryClient()
  const [search, setSearch] = useSearchParams()
  const top = useRef<HTMLElement>(null)
  const settings = useQuery({ queryKey: ['saga-folder'], queryFn: api.sagaFolder })
  const turn = useMutation({
    mutationFn: api.showIssued,
    onSuccess: (saved) => queryClient.setQueryData(['saga-folder'], saved),
    onError: showError,
  })
  // While the answer is on its way the switch already stands where it was turned to.
  const shown = turn.isPending ? turn.variables === true : settings.data?.show_issued === true
  const issued = useQuery({
    queryKey: ['invoices', cui, 'issued'],
    queryFn: () => api.issuedInvoices(cui),
    enabled: shown,
  })
  const invoices = issued.data?.invoices ?? []
  const list = readListState(search, ISSUED)
  const narrowed = filtersOn(list)
  const found = filterInvoices(invoices, list, 'customer')
  const page = pageOf(sortInvoices(found, list.order, 'customer'), list.page, INVOICES_PER_PAGE)
  const change = (changes: Partial<ListState>) => setSearch(writeListState(search, ISSUED, changes), { replace: true })
  const showAll = () => {
    setSearch(clearFilters(search, ISSUED), { replace: true })
    // The button pressed goes away with the filters: the focus goes to the search field.
    document.getElementById('issued-text')?.focus()
  }
  const turnPage = (to: number) => {
    change({ page: to })
    scrollBelowHeader(top.current)
  }

  return (
    <section ref={top} aria-labelledby="issued-invoices" className="flex flex-col gap-3.5 rounded-2xl border bg-card px-5 py-4.5">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <div className="min-w-0 flex-[1_1_420px]">
          <h2 id="issued-invoices" className="font-sans text-lg font-bold">Facturile emise de client</h2>
          {count !== undefined && <p className="text-muted-foreground">{issuedSummary(count)}</p>}
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
      {shown && issued.error && <Notice tone="attention">{errorMessage(issued.error)}</Notice>}
      {shown && issued.isPending && <p role="status" className="text-muted-foreground">Se încarcă facturile emise…</p>}
      {shown && invoices.length > 0 && (
        <>
          <InvoiceFilters id="issued" state={list} party="customer" onChange={change} />
          {narrowed && found.length > 0 && (
            <div className="flex flex-wrap items-center gap-x-4">
              <p role="status" className="text-muted-foreground">{foundLine(found.length, invoices.length)}</p>
              <Button type="button" variant="link" className="px-0" onClick={showAll}>Arată toate facturile emise</Button>
            </div>
          )}
          {found.length > 0 ? (
            <IssuedInvoicesTable invoices={page.items} />
          ) : (
            <div className="rounded-xl border px-5 py-4.5">
              <div role="status">
                <p className="text-lg font-semibold">Nicio factură emisă nu se potrivește cu ce ați ales.</p>
                <p className="text-muted-foreground">Verificați ce ați scris sau perioada.</p>
              </div>
              <Button type="button" variant="link" className="px-0" onClick={showAll}>Arată toate facturile emise</Button>
            </div>
          )}
          <Pager page={page} label="Paginile facturilor emise" line={rangeLine(page, { one: 'Factura', many: 'Facturile' }, narrowed ? 'găsite' : undefined)} onPage={turnPage} />
        </>
      )}
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
                {formatMoney(invoice.total_with_vat, invoice.currency)}
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
