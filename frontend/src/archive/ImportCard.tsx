import { useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { Notice } from '@/components/Notice'
import { scrollBelowHeader } from '@/components/scrollBelowHeader'
import { Button, buttonVariants } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { api } from '../api'
import { errorMessage, showError } from '../errorMessages'
import { formatDate, formatMoney } from '../format'
import { isIssued } from '../invoices/issuedInvoices'
import { listAccount } from '../invoices/lineAccounts'
import type { Invoice, SagaImport } from '../types'
import { opensWindowsHere, useWhere } from '../where'
import { ARCHIVE_TEXT, countsLine, importTitle, sourceLabel, unmarkedLine } from './archiveTexts'

/**
 * One confirmed import: when, by whom, how many invoices, and its file as SAGA got it, to
 * download or show in its folder. Its invoices open under it, each a link to its screen.
 */
export function ImportCard({ entry, cui, startOpen, onToggle }: {
  entry: SagaImport
  cui: string
  startOpen: boolean
  onToggle: (open: boolean) => void // written to the address, so a link back returns to it open
}) {
  const [open, setOpen] = useState(startOpen)
  const toggle = () => {
    setOpen(!open)
    onToggle(!open)
  }
  const card = useRef<HTMLLIElement>(null)
  const detail = useQuery({ queryKey: ['saga-archive-entry', entry.id], queryFn: () => api.sagaArchiveEntry(entry.id), enabled: open })
  const openFolder = useMutation({ mutationFn: () => api.openSagaArchive(entry.id), onError: showError })
  const where = useWhere()
  // Reached from an invoice's screen: the import it went to SAGA in is brought into view.
  useEffect(() => {
    if (startOpen) scrollBelowHeader(card.current)
  }, [startOpen])
  const unmarked = unmarkedLine(entry.unmarked)
  const title = importTitle(entry.imported_at)
  const single = entry.files.length === 1 ? entry.files[0] : null

  return (
    <li ref={card} className="flex flex-col gap-3 rounded-2xl border bg-card px-5 py-4.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <h3 className="font-sans text-lg font-bold">{title}</h3>
        <span
          className={cn(
            'rounded-full px-2.5 py-0.5 text-[0.85rem] font-bold',
            entry.source === 'api' ? 'bg-primary/12 text-primary' : 'bg-muted text-foreground',
          )}
        >
          {sourceLabel(entry.source)}
        </span>
        <span className="text-muted-foreground sm:ml-auto">{countsLine({ ...entry, files: entry.files.length })}</span>
      </div>
      {single && <FileLine importId={entry.id} file={single} />}
      {unmarked && <p className="text-[0.9rem] text-attention-foreground">{unmarked}</p>}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        {/* Named with their import: the same buttons repeat on every card. */}
        <Button variant="link" className="px-0" aria-expanded={open} aria-label={`${open ? 'Ascunde' : 'Arată'} facturile: ${title}`} onClick={toggle}>
          {open ? 'Ascunde facturile' : 'Arată facturile'}
        </Button>
        {/* The archive is the program's own folder: on another computer its files are downloaded instead. */}
        {opensWindowsHere(where) && (
          <Button variant="outline" size="sm" aria-label={`Deschide folderul: ${title}`} disabled={openFolder.isPending} onClick={() => openFolder.mutate()}>
            Deschide folderul
          </Button>
        )}
      </div>
      {open && (
        <div className="flex flex-col gap-3 border-t pt-3">
          {!single && (
            <ul aria-label="Fișierele importului" className="flex flex-col gap-2">
              {entry.files.map((file) => <li key={file.name}><FileLine importId={entry.id} file={file} /></li>)}
            </ul>
          )}
          {detail.error && <Notice tone="attention">{errorMessage(detail.error)}</Notice>}
          {detail.isPending ? (
            <p className="text-muted-foreground">Se încarcă facturile…</p>
          ) : (
            detail.data && <ImportInvoices cui={cui} invoices={detail.data.import.invoices} />
          )}
        </div>
      )}
    </li>
  )
}

/** A file of the import as SAGA got it, to download; or that it is gone from the archive. */
function FileLine({ importId, file }: { importId: number; file: SagaImport['files'][number] }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <span className="min-w-0 rounded-lg bg-background px-3 py-2 font-mono text-[0.85rem] break-all">{file.name}</span>
      {file.present ? (
        // Drawn as the buttons beside it, not in the blue of a link.
        <a className={cn(buttonVariants({ variant: 'outline', size: 'sm' }), 'text-foreground no-underline')} href={api.sagaArchiveFileAddress(importId, file.name)} aria-label={`Descarcă fișierul ${file.name}`} download>
          Descarcă fișierul
        </a>
      ) : (
        <span className="text-[0.9rem] text-muted-foreground">{ARCHIVE_TEXT.gone}</span>
      )}
    </div>
  )
}

/** The invoices of the import, in the order the file held them. */
function ImportInvoices({ cui, invoices }: { cui: string; invoices: Invoice[] }) {
  if (invoices.length === 0) return <p className="text-muted-foreground">Facturile acestui import nu mai sunt în program.</p>
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Factura</TableHead>
            <TableHead>Felul</TableHead>
            <TableHead>Furnizor sau client</TableHead>
            <TableHead>Data</TableHead>
            <TableHead className="text-right">Total</TableHead>
            <TableHead>Cont</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {invoices.map((invoice) => {
            const issued = isIssued(invoice)
            const { main, more } = listAccount(invoice)
            return (
              <TableRow key={invoice.id}>
                <TableCell>
                  <Link to={`/clienti/${cui}/facturi/${invoice.id}`} className="font-semibold">
                    {invoice.invoice_number ?? 'fără număr'}
                  </Link>
                  {!invoice.uploaded_to_accounting && (
                    <span className="block text-[0.85rem] text-attention-foreground">nu mai este marcată ca importată</span>
                  )}
                </TableCell>
                <TableCell>{issued ? 'emisă' : 'primită'}</TableCell>
                <TableCell className="whitespace-normal">{(issued ? invoice.customer_name : invoice.supplier_name) ?? '—'}</TableCell>
                <TableCell className="whitespace-nowrap">{formatDate(invoice.invoice_issue_date)}</TableCell>
                <TableCell className="text-right whitespace-nowrap tabular-nums">{formatMoney(invoice.total_with_vat, invoice.currency)}</TableCell>
                <TableCell className="whitespace-nowrap">
                  <span className="font-bold">{main ?? '—'}</span>
                  {more && <span className="ml-1.5 text-[0.9rem] text-muted-foreground">{more}</span>}
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}
