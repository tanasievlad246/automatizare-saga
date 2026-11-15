import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, Download } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { Notice } from '@/components/Notice'
import { PageTitle } from '@/components/PageTitle'
import { PillTabs } from '@/components/PillTabs'
import { Button } from '@/components/ui/button'
import { api } from '../api'
import { SyncDialog } from '../clients/SyncDialog'
import { errorMessage } from '../errorMessages'
import { formatWhen } from '../format'
import type { Invoice } from '../types'
import { ImportedInSagaCard } from './ImportedInSagaCard'
import { InvoicesTable } from './InvoicesTable'
import { needsAnAccount } from './invoiceState'

// The four ways to look at a client's invoices. The first one that has anything is shown.
const VIEWS = [
  { value: 'noi', label: 'Noi', includes: (invoice: Invoice) => invoice.is_new },
  { value: 'de-verificat', label: 'De verificat', includes: needsAnAccount },
  { value: 'neimportate', label: 'Neimportate în SAGA', includes: (invoice: Invoice) => !invoice.uploaded_to_accounting },
  { value: 'toate', label: 'Toate', includes: () => true },
]

/** One client's received invoices: what is new, what needs an account, what waits for SAGA. */
export function ClientInvoicesPage() {
  const { cui = '' } = useParams()
  const [search, setSearch] = useSearchParams()
  const [syncing, setSyncing] = useState(false)
  const client = useQuery({ queryKey: ['clients'], queryFn: api.clients }).data?.clients.find((each) => each.cui === cui)
  const { data, error, isPending } = useQuery({ queryKey: ['invoices', cui], queryFn: () => api.receivedInvoices(cui) })
  const invoices = data?.invoices ?? []

  const chosen = search.get('arata') ?? VIEWS.find((view) => invoices.some(view.includes))?.value ?? 'toate'
  const shown = invoices.filter(VIEWS.find((view) => view.value === chosen)?.includes ?? (() => true))
  const ready = invoices.filter((invoice) => invoice.classification_status === 'classified' && !invoice.uploaded_to_accounting)

  return (
    <div className="flex flex-col gap-5">
      <Link to="/" className="inline-flex min-h-11 items-center gap-1.5 self-start font-semibold no-underline">
        <ChevronLeft aria-hidden className="size-5" />
        Toți clienții
      </Link>
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3.5">
        <div className="min-w-0 flex-[1_1_320px]">
          <PageTitle title={client?.name ?? `CUI ${cui}`}>
            CUI {cui}
            {client && ` · Ultima descărcare: ${formatWhen(client.last_sync_at)}`}
          </PageTitle>
        </div>
        <Button size="lg" onClick={() => setSyncing(true)}>
          <Download aria-hidden />
          Descarcă facturile
        </Button>
      </div>

      {error && <Notice tone="attention">{errorMessage(error)}</Notice>}
      <PillTabs
        label="Ce facturi se văd"
        value={chosen}
        onChange={(view) => setSearch({ arata: view }, { replace: true })}
        // No counts until the invoices have arrived: "(0)" would read as "none".
        options={VIEWS.map((view) => ({
          value: view.value,
          label: data ? `${view.label} (${invoices.filter(view.includes).length})` : view.label,
        }))}
      />
      {!error && (
        <InvoicesTable
          invoices={shown}
          loading={isPending}
          whenEmpty={
            invoices.length === 0
              ? 'Nu ați descărcat încă facturi pentru acest client. Apăsați „Descarcă facturile”.'
              : 'Nicio factură în această listă. Alegeți altă listă de mai sus.'
          }
        />
      )}
      <ImportedInSagaCard ready={ready} />

      <SyncDialog
        clients={syncing ? [client ?? { cui, name: `CUI ${cui}`, invoices: 0, new_count: 0, review_count: 0, ready_count: 0, last_sync_at: null, enabled: true }] : null}
        someAreOff={false}
        onClose={() => setSyncing(false)}
      />
    </div>
  )
}
