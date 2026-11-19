import { useQuery } from '@tanstack/react-query'
import { ErrorNotice } from '@/components/ErrorNotice'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { api } from '../../api'
import { formatDate, formatMoney } from '../../format'
import { pickerLine, usableInvoices } from './savedInvoices'
import type { Client } from '../../types'

const HOW_MANY = 20

/** The last invoices a client received, to start a trial invoice from one of them. */
export function SavedInvoicePicker({
  client, loading, error, onPick, onClose,
}: {
  client: Client
  /** An invoice has been pressed and is being read. */
  loading: boolean
  error: unknown
  onPick: (invoiceId: string) => void
  onClose: () => void
}) {
  const received = useQuery({ queryKey: ['received-invoices', client.cui], queryFn: () => api.receivedInvoices(client.cui) })
  const invoices = usableInvoices(received.data?.invoices ?? [], HOW_MANY)

  return (
    <Dialog open onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-heading text-3xl">Alegeți o factură salvată</DialogTitle>
          <DialogDescription className="text-lg">
            {pickerLine(invoices.length, client.name)}. Furnizorul și rândurile ei umplu factura de probă;
            factura salvată nu se schimbă.
          </DialogDescription>
        </DialogHeader>
        {received.isPending && <p role="status" className="text-lg text-muted-foreground">Se încarcă…</p>}
        {received.error && <ErrorNotice error={received.error} />}
        {error != null && <ErrorNotice error={error} />}
        {received.data && invoices.length === 0 && <p className="text-lg">Acest client nu are încă facturi primite.</p>}
        <div className="flex max-h-[24rem] flex-col gap-2 overflow-y-auto">
          {invoices.map((invoice) => (
            <button
              key={invoice.id}
              type="button"
              disabled={loading}
              onClick={() => onPick(invoice.id)}
              className="grid min-h-14 cursor-pointer grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-0.5 rounded-lg border-2 border-input bg-card px-4 py-2 text-left hover:bg-muted disabled:cursor-wait disabled:opacity-60"
            >
              <span className="font-bold">{invoice.supplier_name ?? 'Furnizor necunoscut'}</span>
              <span className="text-right whitespace-nowrap">{formatMoney(invoice.total_with_vat, invoice.currency)}</span>
              <span className="text-muted-foreground">{invoice.invoice_number} · {formatDate(invoice.invoice_issue_date)}</span>
            </button>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Renunță</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
