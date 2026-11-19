import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import { api } from '../api'
import { showError } from '../errorMessages'
import type { Invoice, TrialAsk } from '../types'
import { AFTER_A_DECISION } from './afterADecision'
import { DECIDE_AGAIN, NO_JEV, decideAgainChoices, decideAgainPoints } from './decideAgainTexts'
import { isIssued } from './issuedInvoices'

/**
 * The whole invoice decided again from the start, with the rules then Jev, or with Jev alone.
 * It keeps its shape: line by line stays line by line, one account stays one account.
 */
export function DecideAgainDialog({ invoice, lines, jevReady, onClose }: {
  invoice: Invoice
  lines: number // how many lines the invoice has
  jevReady: boolean // an OpenRouter key is set
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const perLine = invoice.line_accounts !== null
  const [ask, setAsk] = useState<TrialAsk>('rules_then_jev')
  const decide = useMutation({
    mutationFn: () => api.classify(invoice.id, true, { ask, perLine }),
    // Returned, so the button stays busy until the invoice has been read again.
    onSuccess: () =>
      Promise.all(AFTER_A_DECISION.map((key) => queryClient.invalidateQueries({ queryKey: [key] }))).then(() => {
        toast.success(DECIDE_AGAIN.done)
        onClose()
      }),
    onError: (error: unknown) => {
      showError(error)
      return queryClient.invalidateQueries({ queryKey: ['invoice'] })
    },
  })
  const busy = decide.isPending
  const party = isIssued(invoice) ? invoice.customer_name : invoice.supplier_name

  return (
    <Dialog open onOpenChange={(isOpen) => !isOpen && !busy && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-heading text-3xl">{DECIDE_AGAIN.title}</DialogTitle>
          <DialogDescription className="text-lg">
            Factura {invoice.invoice_number ?? ''}{party ? ` · ${party}` : ''}
          </DialogDescription>
        </DialogHeader>
        <fieldset className="flex flex-col gap-2.5" disabled={busy}>
          <legend className="mb-2.5 font-bold">{DECIDE_AGAIN.question}</legend>
          {decideAgainChoices(perLine).map((choice) => {
            const off = choice.value === 'jev_only' && !jevReady
            return (
              <label
                key={choice.value}
                className={cn(
                  'flex items-start gap-3 rounded-xl border px-3.5 py-3',
                  ask === choice.value && 'border-2 border-primary bg-primary/5',
                  off ? 'cursor-default opacity-60' : 'cursor-pointer',
                )}
              >
                <input
                  type="radio"
                  name="decide-again"
                  className="mt-1 size-5 shrink-0 accent-primary"
                  checked={ask === choice.value}
                  disabled={off}
                  onChange={() => setAsk(choice.value)}
                />
                <span>
                  <span className="font-bold">{choice.label}</span>
                  <span className="block text-[0.95rem] text-muted-foreground">{off ? NO_JEV : choice.help}</span>
                </span>
              </label>
            )
          })}
        </fieldset>
        <div className="flex flex-col gap-1.5 rounded-xl bg-background px-4.5 py-3.5">
          <p className="font-bold">{DECIDE_AGAIN.happens}</p>
          <ul className="list-disc pl-5">
            {decideAgainPoints({ perLine, lines }).map((point) => <li key={point}>{point}</li>)}
          </ul>
        </div>
        <DialogFooter>
          <Button variant="outline" size="lg" disabled={busy} onClick={onClose}>Renunță</Button>
          <Button size="lg" className="font-bold" disabled={busy} onClick={() => decide.mutate()}>
            {busy ? DECIDE_AGAIN.busy : DECIDE_AGAIN.button}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
