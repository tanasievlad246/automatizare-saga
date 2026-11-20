import { useQuery } from '@tanstack/react-query'
import { Download, RotateCcw } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Notice } from '@/components/Notice'
import { PageTitle } from '@/components/PageTitle'
import { Pager } from '@/components/Pager'
import { pageFrom, pageOf, rangeLine } from '@/components/paging'
import { scrollBelowHeader } from '@/components/scrollBelowHeader'
import { Button } from '@/components/ui/button'
import { api } from '../api'
import { ClassifyAgainDialog } from '../classifyAgain/ClassifyAgainDialog'
import { WHEN_TO_USE, toCheckLine } from '../classifyAgain/classifyAgainTexts'
import { errorMessage } from '../errorMessages'
import { rememberPlace } from '../listPlace'
import { searchWords } from '../textSearch'
import { runningLine } from '../schedule/scheduleTexts'
import { useSchedule } from '../schedule/useSchedule'
import type { Client } from '../types'
import { AddClientDialog } from './AddClientDialog'
import { ClientRow } from './ClientRow'
import { ClientSearchField } from './ClientSearchField'
import { ClientsHeader } from './ClientsHeader'
import { reviewLink } from './clientCounts'
import { byName, onFirst, searchClients, shownLine, whoIsOn } from './clientSearch'
import { ImportClientsDialog } from './ImportClientsDialog'
import { SwitchAllDialog } from './SwitchAllDialog'
import { SyncDialog } from './SyncDialog'
import { switchedOn } from './switchedOff'

/** How many clients one page holds. */
const CLIENTS_PER_PAGE = 20

/** The first screen: every client, what is new for each, and the button that downloads. */
export function ClientsPage() {
  // Read again when the window is returned to, so counts from this morning are not shown as today's.
  const { data, error, isPending } = useQuery({ queryKey: ['clients'], queryFn: api.clients, refetchOnWindowFocus: true })
  const clients = data?.clients ?? []
  // While the program downloads by itself, no download is started by hand.
  const running = useSchedule().data?.running ?? null
  const [clientsToSync, setClientsToSync] = useState<Client[] | null>(null)
  const [clientsToClassify, setClientsToClassify] = useState<Client[] | null>(null)
  const [importing, setImporting] = useState(false)
  const [adding, setAdding] = useState(false)
  // The question before every client is switched: on (true) or off; null while it is not asked.
  const [switchingAll, setSwitchingAll] = useState<boolean | null>(null)
  // Who was on when the list was opened: the order is kept from then, so a client switched on
  // its row stays in place. Taken while drawing, once the clients are here.
  const [atOpen, setAtOpen] = useState<Map<string, boolean> | null>(null)
  if (atOpen === null && data) setAtOpen(whoIsOn(data.clients))
  // What is typed in the search field narrows the rows shown, nothing else: the counts and the
  // download for all clients are still about every client. The search and the page are kept in
  // the address, so "‹ Toți clienții" on a client's screen comes back to them.
  const [search, setSearch] = useSearchParams()
  const typed = search.get('cauta') ?? ''
  const setTyped = (text: string) => setSearch(text ? { cauta: text } : {}, { replace: true }) // a new search starts at its first page
  useEffect(() => rememberPlace('/', search.toString()), [search])
  const searchField = useRef<HTMLInputElement>(null)
  const listTop = useRef<HTMLDivElement>(null)
  const found = searchClients(onFirst(byName(clients), atOpen), typed)
  const seen = shownLine(found.length, clients.length)
  const page = pageOf(found, pageFrom(search.get('pagina')), CLIENTS_PER_PAGE)
  const turnPage = (to: number) => {
    const next = new URLSearchParams(search)
    if (to === 1) next.delete('pagina')
    else next.set('pagina', String(to))
    setSearch(next, { replace: true })
    scrollBelowHeader(listTop.current)
  }
  const showAll = () => {
    setTyped('')
    // The button pressed goes away with the search: the focus goes back to the field.
    searchField.current?.focus()
  }
  const showAllButton = <Button type="button" variant="link" className="px-0" onClick={showAll}>Arată toți clienții</Button>

  const onClients = switchedOn(clients)
  const offCount = clients.length - onClients.length
  const waitingForAnAccount = clients.reduce((total, client) => total + client.review_count, 0)
  const waitingForJev = clients.reduce((total, client) => total + client.waiting_count, 0)
  const firstWaiting = clients.find((client) => client.review_count > 0)
  // Every client with an invoice to check or waiting for Jev, switched on or off: classifying does not ask ANAF.
  const toClassify = clients.filter((client) => client.review_count + client.waiting_count > 0)

  return (
    <div className="flex flex-col gap-6">
      <PageTitle title="Clienți">
        Descărcați de la ANAF facturile primite, pentru toți clienții sau pentru unul singur.
      </PageTitle>

      <div className="flex flex-wrap gap-3">
        {/* The longest label on the page: allowed to wrap, so a narrow window never scrolls sideways. */}
        <Button
          size="lg"
          className="h-auto min-h-14 max-w-full py-2 text-left whitespace-normal"
          disabled={onClients.length === 0 || running !== null}
          onClick={() => setClientsToSync(onClients)}
        >
          <Download aria-hidden />
          Descarcă facturile pentru toți clienții
        </Button>
        <Button size="lg" variant="outline" onClick={() => setImporting(true)}>Importă clienți din Excel</Button>
        <Button size="lg" variant="outline" onClick={() => setAdding(true)}>Adaugă un client</Button>
      </div>
      {running && (
        <Notice tone="fresh" className="-mt-3">
          <p className="text-lg font-semibold">
            {runningLine(running.done, running.total)}
          </p>
          <p>Butoanele de descărcare revin când se termină. Lista se actualizează singură.</p>
        </Notice>
      )}

      {toClassify.length > 0 && (
        <Notice tone="attention" className="flex-wrap items-center">
          <div className="flex flex-col gap-3">
            <p className="text-lg font-semibold">{toCheckLine(waitingForAnAccount, waitingForJev)}</p>
            <div className="flex flex-wrap gap-3">
              {firstWaiting && (
                <Button asChild className="bg-attention-foreground hover:bg-attention-foreground/85">
                  <Link to={reviewLink(firstWaiting)}>Vezi facturile de verificat</Link>
                </Button>
              )}
              <Button
                variant="outline"
                className="h-auto min-h-10 max-w-full border-attention-border bg-card py-2 text-left whitespace-normal"
                disabled={running !== null}
                onClick={() => setClientsToClassify(toClassify)}
              >
                <RotateCcw aria-hidden />
                Clasifică din nou, la toți clienții
              </Button>
            </div>
            <p className="text-[0.9rem]">{WHEN_TO_USE}</p>
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

      {clients.length > 0 && (
        <div ref={listTop} className="flex flex-col gap-3">
          {/* A dash or nothing switches everyone on; a tick, everyone off. */}
          <ClientsHeader on={onClients.length} off={offCount} onPress={() => setSwitchingAll(offCount > 0)} />
          <ClientSearchField ref={searchField} value={typed} onChange={setTyped} />
          {found.length === 0 ? (
            <div className="rounded-2xl border bg-card px-6 py-5.5">
              {/* Only the two sentences are announced, not the button under them. */}
              <div role="status">
                <p className="text-lg font-semibold">Niciun client nu se potrivește cu „{typed.trim()}”.</p>
                <p className="text-muted-foreground">Verificați ce ați scris, sau căutați după CUI.</p>
              </div>
              {showAllButton}
            </div>
          ) : (
            seen && (
              <div className="flex flex-wrap items-center gap-x-4">
                <p role="status" className="text-muted-foreground">{seen}</p>
                {showAllButton}
              </div>
            )
          )}
          {page.items.map((client) => (
            <ClientRow key={client.cui} client={client} blocked={running !== null} onSync={() => setClientsToSync([client])} />
          ))}
          <Pager
            page={page}
            label="Paginile listei de clienți"
            line={rangeLine(page, { one: 'Clientul', many: 'Clienții' }, searchWords(typed).length ? 'găsiți' : undefined)}
            onPage={turnPage}
          />
        </div>
      )}

      <SyncDialog clients={clientsToSync} someAreOff={onClients.length < clients.length} onClose={() => setClientsToSync(null)} />
      {switchingAll !== null && (
        <SwitchAllDialog
          turnOn={switchingAll}
          on={onClients.length}
          off={offCount}
          someHidden={found.length < clients.length}
          onClose={() => setSwitchingAll(null)}
          // Everyone stands the same way now: the order starts again from here.
          onDone={(now) => setAtOpen(whoIsOn(now))}
        />
      )}
      <ClassifyAgainDialog clients={clientsToClassify} onClose={() => setClientsToClassify(null)} />
      <ImportClientsDialog open={importing} onClose={() => setImporting(false)} />
      <AddClientDialog open={adding} onClose={() => setAdding(false)} />
    </div>
  )
}
