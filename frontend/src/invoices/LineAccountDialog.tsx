import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { api } from '../api'
import { showError } from '../errorMessages'
import { formatMoney, formatPercent } from '../format'
import type { Invoice, LineAccount } from '../types'
import { AccountChooser, firstPhrase } from './AccountChooser'

/** What the dialog is about: one line of the invoice, or all of them at once. */
export type LineTarget = { entry: LineAccount; description: string; value: string | null } | 'all'

/** Choosing the account of one line, or one account for every line of the invoice. */
export function LineAccountDialog({
  invoice, target, accounts, onClose,
}: { invoice: Invoice; target: LineTarget; accounts: Record<string, string>; onClose: () => void }) {
  const queryClient = useQueryClient()
  const entry = target === 'all' ? null : target.entry
  const done = {
    // Returned, so the buttons stay busy until the invoice has been read again.
    onSuccess: () =>
      Promise.all(
        ['invoice', 'invoices', 'clients', 'proposed-rules'].map((key) => queryClient.invalidateQueries({ queryKey: [key] })),
      ).then(onClose),
    // The invoice may have changed meanwhile (another tab, a new decision): read it again.
    onError: (error: unknown) => {
      showError(error)
      return queryClient.invalidateQueries({ queryKey: ['invoice'] })
    },
  }
  const accept = useMutation({ mutationFn: () => api.acceptSuggestion(invoice.id, entry?.line), ...done })
  const choose = useMutation({ mutationFn: (cont: string) => api.setCont(invoice.id, cont, false, entry?.line), ...done })
  const busy = accept.isPending || choose.isPending
  const proposed = entry?.suggested_cont && entry.suggested_cont !== entry.cont ? entry.suggested_cont : null

  return (
    <Dialog open onOpenChange={(isOpen) => !isOpen && !busy && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-heading text-3xl">
            {entry ? `Contul pentru linia ${entry.line}` : 'Același cont pe toate liniile'}
          </DialogTitle>
          <DialogDescription className="text-lg">
            {target === 'all'
              ? 'Contul ales înlocuiește conturile tuturor liniilor facturii.'
              : `${target.description} · ${formatMoney(target.value, invoice.currency)}`}
          </DialogDescription>
        </DialogHeader>
        {proposed && entry && (
          <div className="flex flex-col gap-2 rounded-xl bg-fresh px-4 py-3.5 text-fresh-foreground">
            <p className="font-bold">
              Jev propune {proposed}
              {accounts[proposed] ? ` · ${firstPhrase(accounts[proposed])}` : ''}
            </p>
            {entry.confidence !== null && (
              <p>
                {entry.confidence_threshold !== null && entry.confidence < entry.confidence_threshold
                  ? `Este sigur doar ${formatPercent(entry.confidence)}, sub nivelul cerut de ${formatPercent(entry.confidence_threshold)}.`
                  : `Este sigur ${formatPercent(entry.confidence)}.`}
              </p>
            )}
            <Button className="self-start" disabled={busy} onClick={() => accept.mutate()}>Accept propunerea</Button>
          </div>
        )}
        <AccountChooser
          accounts={accounts}
          likelihoods={entry?.probabilities ?? null}
          busy={busy}
          label={proposed ? 'sau alegeți alt cont' : 'Alegeți contul'}
          takeFocus={!proposed}
          onChoose={choose.mutate}
        />
        <DialogFooter>
          <Button variant="outline" size="lg" disabled={busy} onClick={onClose}>Renunță</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
