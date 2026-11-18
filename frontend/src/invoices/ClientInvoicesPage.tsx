import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, Download, RotateCcw } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { Notice } from '@/components/Notice'
import { PageTitle } from '@/components/PageTitle'
import { Pager } from '@/components/Pager'
import { pageOf, rangeLine } from '@/components/paging'
import { scrollBelowHeader } from '@/components/scrollBelowHeader'
import { PillTabs } from '@/components/PillTabs'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { api } from '../api'
import { ClassifyAgainDialog } from '../classifyAgain/ClassifyAgainDialog'
import { WHEN_TO_USE, toCheckLine } from '../classifyAgain/classifyAgainTexts'
import { SyncDialog } from '../clients/SyncDialog'
import { errorMessage, messageForCode } from '../errorMessages'
import { formatWhen } from '../format'
import { placeOf, rememberPlace } from '../listPlace'
import { useSchedule } from '../schedule/useSchedule'
import { SagaArchive } from '../archive/SagaArchive'
import { clientTabs, searchForTab, tabFrom } from '../archive/archiveTexts'
import type { Client, ClientTab, Invoice, InvoiceKind } from '../types'
import { ImportedInSagaCard } from './ImportedInSagaCard'
import { InvoiceFilters } from './InvoiceFilters'
import {
  INVOICES_PER_PAGE, type ListState, accountOptions, clearFilters, filterInvoices, filtersOn, foundLine, readListState,
  sortInvoices, writeListState,
} from './invoiceList'
import { InvoicesTable } from './InvoicesTable'
import { needsAnAccount } from './invoiceState'
import { PerLineSwitch } from './PerLineSwitch'
import { readyForSaga, whenNoneIssued, whenNoneReceived } from './issuedInvoices'

// The four ways to look at a client's invoices. The first one that has anything is shown.
const VIEWS = [
  { value: 'noi', label: 'Noi', includes: (invoice: Invoice) => invoice.is_new },
  { value: 'de-verificat', label: 'De verificat', includes: needsAnAccount },
  { value: 'neimportate', label: 'Neimportate în SAGA', includes: (invoice: Invoice) => !invoice.uploaded_to_accounting },
  { value: 'toate', label: 'Toate', includes: () => true },
]

const INVOICE_NOUN = { one: 'Factura', many: 'Facturile' }

/**
 * One client's invoices, received or issued (two tabs, the received ones first): what is new, what
 * needs an account, what waits for SAGA; found by name, number, days or account, in the order
 * chosen, a page at a time. Under them, the one file for SAGA with both kinds. A third tab,
 * "Arhivă", holds the imports in SAGA confirmed, with their files and invoices.
 */
export function ClientInvoicesPage() {
  const { cui = '' } = useParams()
  const [search, setSearch] = useSearchParams()
  const [syncing, setSyncing] = useState(false)
  const [classifying, setClassifying] = useState(false)
  const listTop = useRef<HTMLDivElement>(null)
  const client = useQuery({ queryKey: ['clients'], queryFn: api.clients }).data?.clients.find((each) => each.cui === cui)
  const tab = tabFrom(search)
  const kind: InvoiceKind = tab === 'issued' ? 'issued' : 'received'
  const party = kind === 'issued' ? 'customer' : 'supplier'
  const received = useQuery({ queryKey: ['invoices', cui], queryFn: () => api.receivedInvoices(cui) })
  // Asked for even while the received ones are shown: the file for SAGA holds both kinds.
  const issued = useQuery({ queryKey: ['invoices', cui, 'issued'], queryFn: () => api.issuedInvoices(cui) })
  const rules = useQuery({ queryKey: ['rules'], queryFn: api.rules }).data
  // Counted on its tab from the start; the archive tab reads the same answer.
  const archive = useQuery({ queryKey: ['saga-archive', cui], queryFn: () => api.sagaArchive(cui) })
  const descriptions = (kind === 'issued' ? rules?.issued_accounts : rules?.accounts) ?? {}
  const { data, error, isPending } = kind === 'issued' ? issued : received
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
  const found = filterInvoices(invoices, list, party)
  const narrowed = filtersOn(list)
  const chosen = search.get('arata') ?? VIEWS.find((view) => found.some(view.includes))?.value ?? 'toate'
  const inView = found.filter(VIEWS.find((view) => view.value === chosen)?.includes ?? (() => true))
  const page = pageOf(sortInvoices(inView, list.order, party), list.page, INVOICES_PER_PAGE)
  // Known once both lists are here: the button must name every invoice the file holds.
  const ready = readyForSaga(received.data?.invoices, issued.data?.invoices)
  // A list that could not be read is said on both tabs: the card for SAGA needs both.
  const problem = error ?? received.error ?? issued.error

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
    document.getElementById('list-text')?.focus()
  }
  // Another tab is another list: it starts whole, at its first page.
  const chooseTab = (wanted: ClientTab) => setSearch(searchForTab(wanted), { replace: true })
  // The import opened last is kept in the address, so the link back from one of its invoices returns to it.
  const openImport = (id: number | null) => {
    const next = new URLSearchParams(search)
    if (id === null) next.delete('import')
    else next.set('import', String(id))
    setSearch(next, { replace: true })
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
      {client && client.review_count + client.waiting_count > 0 && (
        <Notice tone="attention">
          <div className="flex flex-col gap-3">
            <p className="text-lg font-semibold">{toCheckLine(client.review_count, client.waiting_count, client.issued_review_count)}</p>
            <Button
              variant="outline"
              className="h-auto min-h-10 max-w-full self-start border-attention-border bg-card py-2 text-left whitespace-normal"
              disabled={automaticDownloadRuns}
              onClick={() => setClassifying(true)}
            >
              <RotateCcw aria-hidden />
              Clasifică din nou facturile de verificat
            </Button>
            <p className="text-[0.9rem]">{WHEN_TO_USE}</p>
          </div>
        </Notice>
      )}
      {problem && <Notice tone="attention">{errorMessage(problem)}</Notice>}
      <div ref={listTop} className="flex flex-col gap-3.5">
        <KindTabs
          value={tab}
          onChange={chooseTab}
          tabs={clientTabs(received.data?.invoices.length, issued.data?.invoices.length ?? received.data?.issued_count, archive.data?.imports.length)}
        />
        {tab !== 'archive' && <PillTabs
          label="Ce facturi se văd"
          value={chosen}
          onChange={chooseView}
          // No counts until the invoices have arrived: "(0)" would read as "none". Narrowed, they count what was found.
          options={VIEWS.map((view) => ({
            value: view.value,
            label: data ? `${view.label} (${found.filter(view.includes).length})` : view.label,
          }))}
        />}
        {tab !== 'archive' && invoices.length > 0 && (
          <InvoiceFilters
            id="list"
            state={list}
            party={party}
            accounts={accountOptions(invoices, descriptions, list.cont)}
            onChange={change}
            className="rounded-2xl border bg-card px-4.5 py-4"
          />
        )}
        {tab !== 'archive' && narrowed && found.length > 0 && (
          <div className="flex flex-wrap items-center gap-x-4">
            <p role="status" className="text-muted-foreground">{foundLine(found.length, invoices.length)}</p>
            <Button type="button" variant="link" className="px-0" onClick={showAll}>Arată toate facturile</Button>
          </div>
        )}
      </div>
      {tab === 'archive' && <SagaArchive cui={cui} openImport={search.get('import')} onOpenImport={openImport} />}
      {tab !== 'archive' && !error && (narrowed && invoices.length > 0 && found.length === 0 ? (
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
          party={party}
          loading={isPending}
          whenEmpty={
            invoices.length === 0
              ? (kind === 'issued' ? whenNoneIssued : whenNoneReceived)(Boolean(client?.last_sync_at))
              : 'Nicio factură în această listă. Alegeți altă listă de mai sus.'
          }
        />
      ))}
      {tab !== 'archive' && (
        <>
          <Pager page={page} label="Paginile listei de facturi" line={rangeLine(page, INVOICE_NOUN, narrowed ? 'găsite' : undefined)} onPage={turnPage} />
          {ready && <ImportedInSagaCard cui={cui} ready={ready} saga={received.data?.saga} />}
        </>
      )}

      <ClassifyAgainDialog clients={classifying && client ? [client] : null} onClose={() => setClassifying(false)} />
      <SyncDialog
        clients={syncing ? [client ?? unknownClient(cui)] : null}
        someAreOff={false}
        onClose={() => setSyncing(false)}
      />
    </div>
  )
}

/** The two kinds of invoice and the archive, as tabs that stand out from the four lists under them. */
function KindTabs({ value, onChange, tabs }: { value: ClientTab; onChange: (tab: ClientTab) => void; tabs: { value: ClientTab; label: string }[] }) {
  return (
    <div role="group" aria-label="Ce se vede" className="flex flex-wrap gap-1 self-start rounded-xl border bg-card p-1">
      {tabs.map((tab) => (
        <button
          key={tab.value}
          type="button"
          aria-pressed={tab.value === value}
          onClick={() => onChange(tab.value)}
          className={cn(
            'min-h-12 rounded-lg px-5 text-lg font-bold outline-none focus-visible:ring-3 focus-visible:ring-ring/50',
            tab.value === value ? 'bg-primary text-primary-foreground' : 'text-foreground hover:bg-muted',
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}

/** A client not in the list (anymore): enough to download its invoices. */
function unknownClient(cui: string): Client {
  return {
    cui, name: `CUI ${cui}`, invoices: 0, issued_count: 0, new_count: 0, issued_new_count: 0, review_count: 0,
    issued_review_count: 0, waiting_count: 0, ready_count: 0, last_sync_at: null, enabled: true, per_line: false,
  }
}
