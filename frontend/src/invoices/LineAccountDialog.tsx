import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { api } from '../api'
import { showError } from '../errorMessages'
import { formatMoney, formatPercent } from '../format'
import type { Invoice, LineAccount, TrialAsk } from '../types'
import { AccountChooser, firstPhrase } from './AccountChooser'
import { AFTER_A_DECISION } from './afterADecision'
import { LINE_AGAIN, NO_JEV, followersNote } from './decideAgainTexts'

/**
 * What the dialog is about: one line of the invoice, or all of them at once. `followers`: for the
 * largest line, the lines that take its account.
 */
export type LineTarget =
  | { entry: LineAccount; description: string; details: string | null; value: string | null; followers: number[] }
  | 'all'

/**
 * Choosing the account of one line, or one account for every line of the invoice; or one line
 * decided again, with the rules then Jev, or with Jev alone. `jevReady`: an OpenRouter key is set.
 */
export function LineAccountDialog({
  invoice, target, accounts, jevReady, onClose,
}: { invoice: Invoice; target: LineTarget; accounts: Record<string, string>; jevReady: boolean; onClose: () => void }) {
  const queryClient = useQueryClient()
  const entry = target === 'all' ? null : target.entry
  const done = {
    // Returned, so the buttons stay busy until the invoice has been read again.
    onSuccess: () =>
      Promise.all(AFTER_A_DECISION.map((key) => queryClient.invalidateQueries({ queryKey: [key] }))).then(onClose),
    // The invoice may have changed meanwhile (another tab, a new decision): read it again.
    onError: (error: unknown) => {
      showError(error)
      return queryClient.invalidateQueries({ queryKey: ['invoice'] })
    },
  }
  const accept = useMutation({ mutationFn: () => api.acceptSuggestion(invoice.id, entry?.line), ...done })
  const choose = useMutation({ mutationFn: (cont: string) => api.setCont(invoice.id, cont, false, entry?.line), ...done })
  const decideAgain = useMutation({
    mutationFn: (ask: TrialAsk) => api.classify(invoice.id, true, { ask, line: entry?.line, perLine: true }),
    ...done,
    // It may come out as it was (Jev unsure again): the message says it was done all the same.
    onSuccess: () => done.onSuccess().then(() => entry && toast.success(LINE_AGAIN.done(entry.line))),
  })
  const busy = accept.isPending || choose.isPending || decideAgain.isPending
  // A line that only takes the largest line's account has nothing of its own to decide.
  const decidable = entry !== null && entry.method !== 'follows'
  const followers = target === 'all' ? null : followersNote(target.followers)
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
          {target !== 'all' && target.details && <p className="text-muted-foreground">{target.details}</p>}
        </DialogHeader>
        {followers && <p>{followers}</p>}
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
        {decidable && (
          <div className="flex flex-col gap-2.5 border-t pt-4">
            <h3 className="font-sans text-lg font-bold">{LINE_AGAIN.heading}</h3>
            <div className="flex flex-wrap gap-2.5">
              <Button variant="outline" disabled={busy} onClick={() => decideAgain.mutate('rules_then_jev')}>
                {decideAgain.isPending && decideAgain.variables === 'rules_then_jev' ? 'Se hotărăște…' : LINE_AGAIN.rules}
              </Button>
              <Button variant="outline" disabled={busy || !jevReady} onClick={() => decideAgain.mutate('jev_only')}>
                {decideAgain.isPending && decideAgain.variables === 'jev_only' ? 'Se hotărăște…' : LINE_AGAIN.jev}
              </Button>
            </div>
            <p className="text-[0.9rem] text-muted-foreground">{jevReady ? LINE_AGAIN.note : NO_JEV}</p>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" size="lg" disabled={busy} onClick={onClose}>Renunță</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
