import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, Download } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { Notice } from '@/components/Notice'
import { PageTitle } from '@/components/PageTitle'
import { Pager } from '@/components/Pager'
import { pageOf, rangeLine } from '@/components/paging'
import { scrollBelowHeader } from '@/components/scrollBelowHeader'
import { PillTabs } from '@/components/PillTabs'
import { Button } from '@/components/ui/button'
import { api } from '../api'
import { SyncDialog } from '../clients/SyncDialog'
import { errorMessage, messageForCode } from '../errorMessages'
import { formatWhen } from '../format'
import { placeOf, rememberPlace } from '../listPlace'
import { useSchedule } from '../schedule/useSchedule'
import type { Invoice } from '../types'
import { ImportedInSagaCard } from './ImportedInSagaCard'
import { InvoiceFilters } from './InvoiceFilters'
import {
  INVOICES_PER_PAGE, type ListState, accountOptions, clearFilters, filterInvoices, filtersOn, foundLine, readListState,
  sortInvoices, writeListState,
} from './invoiceList'
import { InvoicesTable } from './InvoicesTable'
import { IssuedInvoicesCard } from './IssuedInvoicesCard'
import { needsAnAccount } from './invoiceState'
import { PerLineSwitch } from './PerLineSwitch'
import { whenNoneReceived } from './issuedInvoices'

// The four ways to look at a client's invoices. The first one that has anything is shown.
const VIEWS = [
  { value: 'noi', label: 'Noi', includes: (invoice: Invoice) => invoice.is_new },
  { value: 'de-verificat', label: 'De verificat', includes: needsAnAccount },
  { value: 'neimportate', label: 'Neimportate în SAGA', includes: (invoice: Invoice) => !invoice.uploaded_to_accounting },
  { value: 'toate', label: 'Toate', includes: () => true },
]

const INVOICE_NOUN = { one: 'Factura', many: 'Facturile' }

/**
 * One client's received invoices: what is new, what needs an account, what waits for SAGA; found by
 * name, number, days or account, in the order chosen, a page at a time. Under them, the invoices the
 * client issued, when the person asks to see them.
 */
export function ClientInvoicesPage() {
  const { cui = '' } = useParams()
  const [search, setSearch] = useSearchParams()
  const [syncing, setSyncing] = useState(false)
  const listTop = useRef<HTMLDivElement>(null)
  const client = useQuery({ queryKey: ['clients'], queryFn: api.clients }).data?.clients.find((each) => each.cui === cui)
  const { data, error, isPending } = useQuery({ queryKey: ['invoices', cui], queryFn: () => api.receivedInvoices(cui) })
  const descriptions = useQuery({ queryKey: ['rules'], queryFn: api.rules }).data?.accounts ?? {}
  const invoices = data?.invoices ?? []
  const automaticDownloadRuns = Boolean(useSchedule().data?.running)
  // Why the button is off, if it is: the client is switched off, or the program is downloading by itself.
  const whyNot = client && !client.enabled
    ? messageForCode('client_off')
    : automaticDownloadRuns
      ? 'Programul descarcă acum facturile, singur. Butonul revine când se termină.'
      : null

  // A link back from an invoice, or from the client list, returns to this list as it is now.
  const path = `/clienti/${cui}`
  useEffect(() => rememberPlace(path, search.toString()), [path, search])

  const list = readListState(search)
  const found = filterInvoices(invoices, list, 'supplier')
  const narrowed = filtersOn(list)
  const chosen = search.get('arata') ?? VIEWS.find((view) => found.some(view.includes))?.value ?? 'toate'
  const inView = found.filter(VIEWS.find((view) => view.value === chosen)?.includes ?? (() => true))
  const page = pageOf(sortInvoices(inView, list.order, 'supplier'), list.page, INVOICES_PER_PAGE)
  const ready = invoices.filter((invoice) => invoice.classification_status === 'classified' && !invoice.uploaded_to_accounting)

  // The list chosen is written down with every change, so it does not jump to another while the person narrows it.
  const change = (changes: Partial<ListState>) => {
    const pinned = new URLSearchParams(search)
    if (!pinned.has('arata')) pinned.set('arata', chosen)
    setSearch(writeListState(pinned, '', changes), { replace: true })
  }
  // Another list starts at its first page; the search, days, account and order stay.
  const chooseView = (view: string) => {
    const next = writeListState(search, '', { page: 1 })
    next.set('arata', view)
    setSearch(next, { replace: true })
  }
  const showAll = () => {
    setSearch(clearFilters(search, ''), { replace: true })
    // The button pressed goes away with the filters: the focus goes to the search field.
    document.getElementById('received-text')?.focus()
  }
  const turnPage = (to: number) => {
    change({ page: to })
    scrollBelowHeader(listTop.current)
  }

  return (
    <div className="flex flex-col gap-5">
      <Link to={placeOf('/')} className="inline-flex min-h-11 items-center gap-1.5 self-start font-semibold no-underline">
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
        <div className="flex max-w-md flex-col items-start gap-2">
          <Button size="lg" disabled={whyNot !== null} onClick={() => setSyncing(true)}>
            <Download aria-hidden />
            Descarcă facturile
          </Button>
          {whyNot && <p className="text-muted-foreground">{whyNot}</p>}
        </div>
      </div>

      {client && <PerLineSwitch client={client} />}
      {error && <Notice tone="attention">{errorMessage(error)}</Notice>}
      <div ref={listTop} className="flex flex-col gap-3.5">
        <PillTabs
          label="Ce facturi se văd"
          value={chosen}
          onChange={chooseView}
          // No counts until the invoices have arrived: "(0)" would read as "none". Narrowed, they count what was found.
          options={VIEWS.map((view) => ({
            value: view.value,
            label: data ? `${view.label} (${found.filter(view.includes).length})` : view.label,
          }))}
        />
        {invoices.length > 0 && (
          <InvoiceFilters
            id="received"
            state={list}
            party="supplier"
            accounts={accountOptions(invoices, descriptions, list.cont)}
            onChange={change}
            className="rounded-2xl border bg-card px-4.5 py-4"
          />
        )}
        {narrowed && found.length > 0 && (
          <div className="flex flex-wrap items-center gap-x-4">
            <p role="status" className="text-muted-foreground">{foundLine(found.length, invoices.length)}</p>
            <Button type="button" variant="link" className="px-0" onClick={showAll}>Arată toate facturile</Button>
          </div>
        )}
      </div>
      {!error && (narrowed && invoices.length > 0 && found.length === 0 ? (
        <div className="rounded-2xl border bg-card px-6 py-5.5">
          <div role="status">
            <p className="text-lg font-semibold">Nicio factură nu se potrivește cu ce ați ales.</p>
            <p className="text-muted-foreground">Verificați ce ați scris, perioada sau contul.</p>
          </div>
          <Button type="button" variant="link" className="px-0" onClick={showAll}>Arată toate facturile</Button>
        </div>
      ) : (
        <InvoicesTable
          invoices={page.items}
          loading={isPending}
          whenEmpty={
            invoices.length === 0
              ? whenNoneReceived(Boolean(client?.last_sync_at))
              : 'Nicio factură în această listă. Alegeți altă listă de mai sus.'
          }
        />
      ))}
      <Pager page={page} label="Paginile listei de facturi" line={rangeLine(page, INVOICE_NOUN, narrowed ? 'găsite' : undefined)} onPage={turnPage} />
      <ImportedInSagaCard cui={cui} ready={ready} saga={data?.saga} />
      <IssuedInvoicesCard cui={cui} count={data?.issued_count} />

      <SyncDialog
        clients={syncing ? [client ?? { cui, name: `CUI ${cui}`, invoices: 0, new_count: 0, review_count: 0, ready_count: 0, last_sync_at: null, enabled: true, per_line: false }] : null}
        someAreOff={false}
        onClose={() => setSyncing(false)}
      />
    </div>
  )
}
