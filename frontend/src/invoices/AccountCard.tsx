import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Check } from 'lucide-react'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { api } from '../api'
import { errorMessage, showError } from '../errorMessages'
import { formatPercent } from '../format'
import type { Invoice, InvoiceView } from '../types'
import { AccountChooser, firstPhrase } from './AccountChooser'

const WHO_CHOSE: Record<string, (invoice: Invoice) => string> = {
  rules: () => 'Ales de o regulă a dumneavoastră',
  jev: (invoice) => `Ales de Jev, sigur ${formatPercent(invoice.confidence)}`,
  jev_accepted: () => 'Propus de Jev și acceptat de dumneavoastră',
  human: () => 'Ales de dumneavoastră',
}

/** The account of one invoice: what it is and who chose it, or the question when nobody has. */
export function AccountCard({
  invoice, jev, accounts,
}: { invoice: Invoice; jev: InvoiceView['jev']; accounts: Record<string, string> }) {
  const queryClient = useQueryClient()
  const [changing, setChanging] = useState(false)
  const afterChange = {
    onSuccess: () => {
      setChanging(false)
      // A new account can also bring, change or remove a proposed rule.
      for (const key of ['invoice', 'invoices', 'clients', 'proposed-rules']) queryClient.invalidateQueries({ queryKey: [key] })
    },
    onError: showError,
  }
  const accept = useMutation({ mutationFn: () => api.acceptSuggestion(invoice.id), ...afterChange })
  // An invoice saved before accounts were chosen automatically has no state at all; the
  // program changes those only when told the person really means it.
  const outsideClassification = invoice.classification_status === null
  const choose = useMutation({
    mutationFn: (cont: string) => api.setCont(invoice.id, cont, outsideClassification),
    ...afterChange,
  })
  const decide = useMutation({
    mutationFn: () => api.classify(invoice.id, outsideClassification),
    ...afterChange,
  })
  const busy = accept.isPending || choose.isPending || decide.isPending
  const chooser = (
    <AccountChooser accounts={accounts} likelihoods={jev?.probabilities ?? null} busy={busy} onChoose={choose.mutate} />
  )

  // The program holds back an invoice it has seen before (same supplier, number and date)
  // without asking Jev, so there is neither a proposal nor a confidence.
  const sentTwice =
    invoice.classification_status === 'review' &&
    invoice.possible_duplicate_of !== null &&
    invoice.suggested_cont === null &&
    invoice.confidence === null
  if (sentTwice && !invoice.uploaded_to_accounting) {
    return (
      <section aria-label="Contul facturii" className="overflow-hidden rounded-2xl border-2 border-attention-border bg-card">
        <h2 className="bg-attention px-5 py-3.5 font-sans text-xl font-bold text-attention-foreground">
          Factura pare trimisă de două ori
        </h2>
        <div className="flex flex-col gap-3.5 px-5 pt-4.5 pb-5.5">
          <p>
            Are același furnizor, același număr și aceeași dată ca o factură salvată mai devreme. Verificați, ca să
            nu o înregistrați de două ori în SAGA.
          </p>
          <Button asChild variant="outline" className="h-auto min-h-12 self-start py-2 text-left whitespace-normal">
            <Link to={`/clienti/${invoice.cui}/facturi/${invoice.possible_duplicate_of}`}>Vezi factura salvată mai devreme</Link>
          </Button>
          <p>
            Dacă este aceeași factură, bifați mai jos „Am importat factura în SAGA” și nu va mai apărea la verificat.
            Dacă este altă factură, alegeți-i contul:
          </p>
          {chooser}
        </div>
      </section>
    )
  }

  if (invoice.classification_status === 'review' && !invoice.uploaded_to_accounting) {
    const proposed = invoice.suggested_cont
    return (
      <section aria-label="Contul facturii" className="overflow-hidden rounded-2xl border-2 border-attention-border bg-card">
        <h2 className="bg-attention px-5 py-3.5 font-sans text-xl font-bold text-attention-foreground">
          Trebuie să alegeți contul
        </h2>
        <div className="flex flex-col gap-3.5 px-5 pt-4.5 pb-5.5">
          {proposed ? (
            <>
              <BigAccount label="Jev propune" cont={proposed} description={accounts[proposed]} />
              <p>
                {invoice.confidence === null
                  ? 'Jev nu a spus cât de sigur este.'
                  : `Jev este sigur doar ${formatPercent(invoice.confidence)}. Sub ${formatPercent(invoice.confidence_threshold)} vă întreabă pe dumneavoastră.`}
              </p>
              <Button size="lg" className="font-bold" disabled={busy} onClick={() => accept.mutate()}>
                Da, contul {proposed} este bun
              </Button>
            </>
          ) : (
            <>
              <p>Programul nu a putut alege singur contul acestei facturi.</p>
              <TechnicalDetail text={invoice.classification_reason} />
            </>
          )}
          {chooser}
        </div>
      </section>
    )
  }

  return (
    <section aria-label="Contul facturii" className="flex flex-col gap-3 rounded-2xl border bg-card px-5 pt-4.5 pb-5.5">
      {invoice.cont ? (
        <>
          <BigAccount label="Contul facturii" cont={invoice.cont} description={accounts[invoice.cont]} />
          <p className="flex items-center gap-2 font-semibold text-done-foreground">
            <Check aria-hidden className="size-5" />
            {WHO_CHOSE[invoice.classification_method ?? '']?.(invoice)}
          </p>
        </>
      ) : (
        <>
          <h2 className="font-sans text-xl font-bold">Factura nu are încă un cont</h2>
          {invoice.classification_status === 'pending' && (
            <>
              <p>Programul nu a reușit să îl întrebe pe Jev. Va încerca din nou la următoarea descărcare.</p>
              <TechnicalDetail text={invoice.classification_error} />
            </>
          )}
        </>
      )}

      {invoice.uploaded_to_accounting ? (
        <p className="text-muted-foreground">Factura este importată în SAGA, așa că aici contul nu se mai schimbă.</p>
      ) : invoice.cont && !changing ? (
        <Button variant="outline" className="self-start" onClick={() => setChanging(true)}>Schimbă contul</Button>
      ) : (
        <>
          {!invoice.cont && (
            <Button className="self-start" disabled={busy} onClick={() => decide.mutate()}>
              {decide.isPending ? 'Se alege…' : 'Alege contul automat'}
            </Button>
          )}
          {decide.error && <p className="text-attention-foreground">{errorMessage(decide.error)}</p>}
          {chooser}
        </>
      )}
    </section>
  )
}

function BigAccount({ label, cont, description }: { label: string; cont: string; description?: string }) {
  return (
    <div>
      <div className="text-[0.9rem] font-semibold text-muted-foreground">{label}</div>
      <div className="flex flex-wrap items-baseline gap-x-3">
        <span className="font-heading text-[2.4rem] leading-tight font-bold">{cont}</span>
        <span className="font-semibold">{firstPhrase(description)}</span>
      </div>
    </div>
  )
}

/** The program's own English explanation, kept small for whoever is asked to help. */
function TechnicalDetail({ text }: { text: string | null }): ReactNode {
  return text ? <p className="text-[0.9rem] text-muted-foreground">Detalii tehnice: {text}</p> : null
}
