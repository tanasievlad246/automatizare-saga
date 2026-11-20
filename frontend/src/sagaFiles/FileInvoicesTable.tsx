import { ArrowDown, ArrowUp, ArrowUpDown, ChevronDown, ChevronRight } from 'lucide-react'
import { Fragment, useEffect, useState } from 'react'
import { Link } from 'react-router'
import { Pager } from '@/components/Pager'
import { pageOf, rangeLine } from '@/components/paging'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { formatDate, formatMoney } from '../format'
import { INVOICES_PER_PAGE } from '../invoices/invoiceList'
import { listAccount } from '../invoices/lineAccounts'
import type { Invoice } from '../types'
import { InvoiceLines } from './InvoiceLines'
import { recallTable, rememberTable } from './tableMemory'
import {
  COLUMNS, FILES_TAB, type Sort, type SortColumn, kindOf, nextSort, partyOf, sortFileInvoices, sortLabel, sortedLine,
} from './waitingFiles'

const INVOICE_NOUN = { one: 'Factura', many: 'Facturile' }

/**
 * The invoices of one file for SAGA, a page at a time, in the order of the file until a column's
 * heading is pressed. The arrow in front of an invoice shows its lines in the rows under it.
 * `memory` names the table (the client and the file): how it is left is found again after a
 * look at one of its invoices.
 */
export function FileInvoicesTable({ fileName, memory, invoices }: { fileName: string; memory: string; invoices: Invoice[] }) {
  const [sort, setSort] = useState<Sort | null>(() => recallTable(memory).sort)
  const [wanted, setWanted] = useState(() => recallTable(memory).page)
  const [open, setOpen] = useState<ReadonlySet<string>>(() => new Set(recallTable(memory).open))
  useEffect(() => rememberTable(memory, { sort, page: wanted, open: [...open] }), [memory, sort, wanted, open])
  const page = pageOf(sortFileInvoices(invoices, sort), wanted, INVOICES_PER_PAGE)
  // One invoice: nothing to put in order, so the headings are plain words.
  const sortable = invoices.length > 1
  // Another order starts at its first page; the rows that are open stay open.
  const order = (next: Sort | null) => {
    setSort(next)
    setWanted(1)
  }
  const toggle = (id: string) =>
    setOpen((now) => {
      const next = new Set(now)
      if (!next.delete(id)) next.add(id)
      return next
    })

  return (
    <div className="flex flex-col gap-2.5">
      {/* A container, so the lines under an open invoice can be as wide as what is seen of the table. */}
      <div className="@container overflow-hidden rounded-xl border">
        <Table className="min-w-[760px]">
          <TableHeader>
            <TableRow>
              <TableHead className="w-14"><span className="sr-only">Liniile facturii</span></TableHead>
              {COLUMNS.map(({ column, label, numeric }) => (
                <TableHead
                  key={column}
                  className={cn(numeric && 'text-right')}
                  aria-sort={sort?.column === column ? (sort.direction === 'asc' ? 'ascending' : 'descending') : undefined}
                >
                  {sortable ? <SortButton label={label} column={column} sort={sort} onPress={() => order(nextSort(sort, column))} /> : label}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {page.items.map((invoice) => {
              const isOpen = open.has(invoice.id)
              const number = invoice.invoice_number ?? 'fără număr'
              const { main, more } = listAccount(invoice)
              return (
                <Fragment key={invoice.id}>
                  <TableRow>
                    <TableCell>
                      <Button
                        variant={isOpen ? 'default' : 'outline'} size="icon" className="size-10"
                        aria-expanded={isOpen}
                        aria-label={`${isOpen ? 'Ascunde' : 'Arată'} liniile facturii ${number}`}
                        onClick={() => toggle(invoice.id)}
                      >
                        {isOpen ? <ChevronDown aria-hidden /> : <ChevronRight aria-hidden />}
                      </Button>
                    </TableCell>
                    <TableCell>
                      <Link to={`/clienti/${invoice.cui}/facturi/${invoice.id}`} className="font-semibold">{number}</Link>
                    </TableCell>
                    <TableCell>{kindOf(invoice)}</TableCell>
                    <TableCell className="whitespace-normal">{partyOf(invoice) ?? '—'}</TableCell>
                    <TableCell className="whitespace-nowrap">{formatDate(invoice.invoice_issue_date)}</TableCell>
                    <TableCell className="text-right whitespace-nowrap tabular-nums">{formatMoney(invoice.total_with_vat, invoice.currency)}</TableCell>
                    <TableCell className="whitespace-nowrap">
                      <span className="font-bold">{main ?? '—'}</span>
                      {more && <span className="ml-1.5 text-[0.9rem] text-muted-foreground">{more}</span>}
                    </TableCell>
                  </TableRow>
                  {isOpen && (
                    <TableRow className="hover:bg-transparent">
                      <TableCell colSpan={COLUMNS.length + 1} className="p-0 whitespace-normal">
                        {/* On a narrow screen the table scrolls sideways; the lines stay in sight, at the width seen. */}
                        <div className="sticky left-0 w-[calc(100cqw-2px)]">
                          <InvoiceLines invoiceId={invoice.id} cui={invoice.cui} number={number} />
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                </Fragment>
              )
            })}
          </TableBody>
        </Table>
      </div>
      {sortable && (
        <div className="flex flex-wrap items-center gap-x-4">
          <p role="status" className="text-[0.9rem] text-muted-foreground">{sort ? sortedLine(sort) : FILES_TAB.fileOrder}</p>
          {sort && <Button type="button" variant="link" className="px-0" onClick={() => order(null)}>{FILES_TAB.backToFileOrder}</Button>}
        </div>
      )}
      <Pager page={page} label={`Paginile facturilor din fișierul ${fileName}`} line={rangeLine(page, INVOICE_NOUN)} onPage={setWanted} />
    </div>
  )
}

/** A column's heading as a button: its arrow says which way the table is ordered by it, if it is. */
function SortButton({ label, column, sort, onPress }: { label: string; column: SortColumn; sort: Sort | null; onPress: () => void }) {
  const active = sort?.column === column
  const Arrow = !active ? ArrowUpDown : sort.direction === 'asc' ? ArrowUp : ArrowDown
  return (
    <button
      type="button"
      aria-label={sortLabel(label, sort, column)}
      onClick={onPress}
      className={cn(
        '-mx-2 inline-flex min-h-10 items-center gap-1.5 rounded-lg px-2 font-semibold outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50',
        active ? 'bg-muted text-foreground' : 'text-muted-foreground',
      )}
    >
      {label}
      <Arrow aria-hidden className={cn('size-4', !active && 'opacity-60')} />
    </button>
  )
}
