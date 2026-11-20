import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { api } from '../api'
import { showError } from '../errorMessages'
import { formatMoney } from '../format'
import { AccountChooser, firstPhrase } from '../invoices/AccountChooser'
import { AFTER_A_DECISION } from '../invoices/afterADecision'
import type { Invoice } from '../types'
import { partyOf } from './waitingFiles'

/**
 * Another account for an invoice that has one account for all its lines, chosen among the files
 * waiting for SAGA. Only an account is chosen here; deciding again is on the invoice's own screen.
 */
export function InvoiceAccountDialog({
  invoice, accounts, likelihoods, onClose,
}: { invoice: Invoice; accounts: Record<string, string>; likelihoods: Record<string, number> | null; onClose: () => void }) {
  const queryClient = useQueryClient()
  const choose = useMutation({
    mutationFn: (cont: string) => api.setCont(invoice.id, cont),
    // Returned, so the button stays busy until the file and the lists have been read again.
    onSuccess: () =>
      Promise.all(AFTER_A_DECISION.map((key) => queryClient.invalidateQueries({ queryKey: [key] }))).then(onClose),
    // The invoice may have changed meanwhile (another tab, a download): read it again.
    onError: (error: unknown) => {
      showError(error)
      return queryClient.invalidateQueries({ queryKey: ['invoice'] })
    },
  })
  const described = invoice.cont ? firstPhrase(accounts[invoice.cont]) : ''

  return (
    <Dialog open onOpenChange={(isOpen) => !isOpen && !choose.isPending && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-heading text-3xl">Contul facturii {invoice.invoice_number ?? ''}</DialogTitle>
          <DialogDescription className="text-lg">
            {partyOf(invoice) ?? 'fără nume'} · {formatMoney(invoice.total_with_vat, invoice.currency)}
          </DialogDescription>
        </DialogHeader>
        <p>
          Acum factura are contul <strong>{invoice.cont}</strong>
          {described && ` (${described})`}. Contul ales se pune pe toate liniile ei.
        </p>
        <AccountChooser
          accounts={accounts}
          likelihoods={likelihoods}
          busy={choose.isPending}
          label="Alegeți alt cont"
          takeFocus
          onChoose={choose.mutate}
        />
        <DialogFooter>
          <Button variant="outline" size="lg" disabled={choose.isPending} onClick={onClose}>Renunță</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
