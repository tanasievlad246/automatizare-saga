import { useQuery } from '@tanstack/react-query'
import { Download } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { Notice } from '@/components/Notice'
import { PageTitle } from '@/components/PageTitle'
import { Button } from '@/components/ui/button'
import { api } from '../api'
import { errorMessage } from '../errorMessages'
import { countOf } from '../format'
import type { Client } from '../types'
import { AddClientDialog } from './AddClientDialog'
import { ClientRow } from './ClientRow'
import { ImportClientsDialog } from './ImportClientsDialog'
import { SyncDialog } from './SyncDialog'

/** The first screen: every client, what is new for each, and the button that downloads. */
export function ClientsPage() {
  // Read again when the window is returned to, so counts from this morning are not shown as today's.
  const { data, error, isPending } = useQuery({ queryKey: ['clients'], queryFn: api.clients, refetchOnWindowFocus: true })
  const clients = data?.clients ?? []
  const [clientsToSync, setClientsToSync] = useState<Client[] | null>(null)
  const [importing, setImporting] = useState(false)
  const [adding, setAdding] = useState(false)

  const waitingForAnAccount = clients.reduce((total, client) => total + client.review_count, 0)
  const firstWaiting = clients.find((client) => client.review_count > 0)

  return (
    <div className="flex max-w-[66rem] flex-col gap-6">
      <PageTitle title="Clienți">
        Descărcați de la ANAF facturile primite, pentru toți clienții sau pentru unul singur.
      </PageTitle>

      <div className="flex flex-wrap gap-3">
        {/* The longest label on the page: allowed to wrap, so a narrow window never scrolls sideways. */}
        <Button
          size="lg"
          className="h-auto min-h-14 max-w-full py-2 text-left whitespace-normal"
          disabled={clients.length === 0}
          onClick={() => setClientsToSync(clients)}
        >
          <Download aria-hidden />
          Descarcă facturile pentru toți clienții
        </Button>
        <Button size="lg" variant="outline" onClick={() => setImporting(true)}>Importă clienți din Excel</Button>
        <Button size="lg" variant="outline" onClick={() => setAdding(true)}>Adaugă un client</Button>
      </div>

      {firstWaiting && (
        <Notice tone="attention" className="flex-wrap items-center">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
            <p className="min-w-0 flex-[1_1_320px] text-lg font-semibold">
              {countOf(
                waitingForAnAccount,
                'O factură este de verificat: trebuie să îi alegeți contul.',
                'facturi sunt de verificat: trebuie să le alegeți contul.',
              )}
            </p>
            <Button asChild className="bg-attention-foreground hover:bg-attention-foreground/85">
              <Link to={`/clienti/${firstWaiting.cui}?arata=de-verificat`}>Vezi facturile de verificat</Link>
            </Button>
          </div>
        </Notice>
      )}

      {error && <Notice tone="attention">{errorMessage(error)}</Notice>}
      {isPending && <p role="status" className="text-lg text-muted-foreground">Se încarcă clienții…</p>}
      {!isPending && !error && clients.length === 0 && (
        <p className="rounded-2xl border bg-card px-6 py-8 text-lg">
          Nu aveți încă niciun client. Importați lista din Excel sau adăugați primul client.
        </p>
      )}

      <div className="flex flex-col gap-3">
        {clients.map((client) => (
          <ClientRow key={client.cui} client={client} onSync={() => setClientsToSync([client])} />
        ))}
      </div>

      <SyncDialog clients={clientsToSync} onClose={() => setClientsToSync(null)} />
      <ImportClientsDialog open={importing} onClose={() => setImporting(false)} />
      <AddClientDialog open={adding} onClose={() => setAdding(false)} />
    </div>
  )
}
