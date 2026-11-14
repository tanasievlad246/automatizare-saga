import { useQuery } from '@tanstack/react-query'
import { ChevronLeft } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { Notice } from '@/components/Notice'
import { PageTitle } from '@/components/PageTitle'
import { PillTabs } from '@/components/PillTabs'
import { api } from '../api'
import { errorMessage } from '../errorMessages'
import { formatDate, formatMoney } from '../format'
import { ProposedRuleCard } from '../rules/ProposedRuleCard'
import { AccountCard } from './AccountCard'
import { InvoiceStateBadges } from './InvoiceStateBadges'
import { RenderedInvoice } from './RenderedInvoice'
import { SagaFileCard } from './SagaFileCard'
import { XmlViewer } from './XmlViewer'

type Shown = 'factura' | 'anaf' | 'saga'
const WAYS_TO_SEE_IT: { value: Shown; label: string }[] = [
  { value: 'factura', label: 'Factura' },
  { value: 'anaf', label: 'Fișierul de la ANAF (XML)' },
  { value: 'saga', label: 'Fișierul pentru SAGA (XML)' },
]

/** One invoice: what it says, the two files behind it, its account and its file for SAGA. */
export function InvoicePage() {
  const { cui = '', id = '' } = useParams()
  const [shown, setShown] = useState<Shown>('factura')
  const { data: view, error } = useQuery({ queryKey: ['invoice', id], queryFn: () => api.invoiceView(id) })
  const accounts = useQuery({ queryKey: ['rules'], queryFn: api.rules }).data?.accounts ?? {}

  const back = (
    <Link to={`/clienti/${cui}`} className="inline-flex min-h-11 items-center gap-1.5 self-start font-semibold no-underline">
      <ChevronLeft aria-hidden className="size-5" />
      Facturile clientului {view?.client_name ?? `cu CUI ${cui}`}
    </Link>
  )
  if (error) return <div className="flex flex-col gap-5">{back}<Notice tone="attention">{errorMessage(error)}</Notice></div>
  if (!view) {
    return (
      <div className="flex flex-col gap-5">
        {back}
        <p role="status" className="text-lg text-muted-foreground">Se încarcă factura…</p>
      </div>
    )
  }

  const { invoice, document } = view
  return (
    <div className="flex flex-col gap-5">
      {back}
      <div className="flex flex-wrap items-start gap-x-6 gap-y-3">
        <div className="min-w-0 flex-[1_1_320px]">
          <PageTitle title={`Factura ${invoice.invoice_number ?? ''}`}>
            de la {invoice.supplier_name} · {formatDate(invoice.invoice_issue_date)} ·{' '}
            {formatMoney(invoice.total_payable, invoice.currency)}
          </PageTitle>
        </div>
        <InvoiceStateBadges invoice={invoice} />
      </div>

      {/* Two columns when there is room for both. Otherwise one, with the account first:
          it is what the person came for, and must not end up under a long invoice. */}
      <div className="@container">
      <div className="grid items-start gap-5 @[58rem]:grid-cols-[minmax(0,1fr)_23rem]">
        <section aria-label="Factura" className="min-w-0 rounded-2xl border bg-card @max-[58rem]:order-last">
          <div className="border-b px-4 py-3.5">
            <PillTabs label="Cum se vede factura" options={WAYS_TO_SEE_IT} value={shown} onChange={setShown} />
          </div>
          {shown === 'factura' &&
            (document ? (
              <RenderedInvoice document={document} />
            ) : (
              <p className="px-6 py-6 text-muted-foreground">Acest mesaj de la ANAF nu este o factură.</p>
            ))}
          {shown === 'anaf' && (
            <XmlViewer
              xml={view.xml}
              explanation="Așa a venit factura de la ANAF. Nu se poate modifica."
              whenMissing="Fișierul de la ANAF nu a fost păstrat."
            />
          )}
          {shown === 'saga' && (
            <XmlViewer
              xml={view.saga_xml}
              explanation="Acesta este fișierul pe care îl importă SAGA. Fiecare linie are contul ales."
              whenMissing="Fișierul pentru SAGA se creează după ce factura are un cont."
            />
          )}
        </section>
        <div className="flex min-w-0 flex-col gap-5">
          <AccountCard invoice={invoice} jev={view.jev} accounts={accounts} />
          {view.rule_suggestion && (
            // Another invoice, or another account for this one, is a different proposal: start it afresh.
            <ProposedRuleCard
              key={`${invoice.id} ${view.rule_suggestion.cont}`}
              invoice={invoice}
              suggestion={view.rule_suggestion}
            />
          )}
          <SagaFileCard invoice={invoice} />
        </div>
      </div>
      </div>
    </div>
  )
}
