import { keepPreviousData, useInfiniteQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { ErrorNotice } from '@/components/ErrorNotice'
import { Notice } from '@/components/Notice'
import { PageTitle } from '@/components/PageTitle'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { api } from '../api'
import type { JournalFilter } from '../api'
import { formatDate, today } from '../format'
import type { TechnicalCounts } from '../types'
import { JournalEntry } from './JournalEntry'
import { JournalFilters } from './JournalFilters'
import type { JournalChoice } from './JournalFilters'
import { filterFor } from './journalFilter'
import { operationSummary, timeline } from './technical'
import type { TimelineItem } from './technical'
import { TechnicalEntry } from './TechnicalEntry'

const EVERYTHING: JournalChoice = { shown: 'tot', details: false, area: '', period: 'azi', text: '' }

/**
 * What the program did, newest first. One operation can be shown whole, in the order it happened.
 * The technical view, for whoever looks into how the program works, adds each request to ANAF and
 * Jev and the program's own records to an operation's steps. It is off whenever the page opens.
 */
export function JournalPage() {
  const [choice, setChoice] = useState(EVERYTHING)
  // The operation being looked at, if any, and the technical view are in the address, so that a
  // link can open them and Back leaves them; the view stays on from the list to an operation.
  const [params, setParams] = useSearchParams()
  const operation = params.get('operatiune') || null
  const technical = params.get('tehnic') === '1'
  const change = (name: string, value: string | null) =>
    setParams((current) => {
      const next = new URLSearchParams(current)
      if (value) next.set(name, value)
      else next.delete(name)
      return next
    })
  const setOperation = (trace: string | null) => change('operatiune', trace)
  const setTechnical = (on: boolean) => change('tehnic', on ? '1' : null)

  const filter: JournalFilter = { ...(operation ? { trace: operation } : filterFor(choice)), ...(technical ? { technical } : {}) }
  const journal = useInfiniteQuery({
    queryKey: ['journal', filter],
    queryFn: ({ pageParam }) => api.journal(filter, pageParam),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (last) => (last.has_more ? last.events.at(-1)?.id : undefined),
    placeholderData: keepPreviousData, // the list stays while the next answer is on its way
    refetchOnWindowFocus: true,
  })
  const records = useInfiniteQuery({
    queryKey: ['journal-technical', operation],
    queryFn: ({ pageParam }) => api.technical(operation!, pageParam),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (last) => (last.has_more ? last.records.at(-1)?.id : undefined),
    enabled: technical && operation !== null,
    refetchOnWindowFocus: true,
  })
  const withRecords = technical && operation !== null
  const lines = journal.data?.pages.flatMap((page) => page.events) ?? []
  const counts: TechnicalCounts = Object.assign({}, ...(journal.data?.pages.map((page) => page.technical ?? {}) ?? []))
  const recordList = withRecords ? (records.data?.pages.flatMap((page) => page.records) ?? []).reverse() : []
  // One operation is read from its first step to its last; everything else newest first.
  const inOrder = operation ? [...lines].reverse() : lines
  const items: TimelineItem[] = withRecords
    ? timeline(inOrder, !journal.hasNextPage, recordList, !records.hasNextPage)
    : inOrder.map((line) => ({ kind: 'line', line }))
  const summary = withRecords && records.data ? operationSummary(recordList) : null

  const hasOlder = journal.hasNextPage || (withRecords && records.hasNextPage)
  const loadingOlder = journal.isFetchingNextPage || records.isFetchingNextPage
  const readOlder = () => {
    if (journal.hasNextPage) journal.fetchNextPage()
    if (withRecords && records.hasNextPage) records.fetchNextPage()
  }
  // Older lines are read on request. In one operation they are its earlier steps, which
  // come in at the top, so the button is above the list there, and below it everywhere else.
  const older = hasOlder && (
    <div className={operation ? 'px-4.5 py-3.5' : 'border-t px-4.5 py-3.5'}>
      <Button variant="outline" disabled={loadingOlder} onClick={readOlder}>
        {loadingOlder ? 'Se încarcă…' : operation ? 'Arată pașii de dinainte' : 'Arată mai vechi'}
      </Button>
    </div>
  )
  const reading = journal.isFetching || (withRecords && records.isFetching)

  return (
    <div className="flex flex-col gap-5">
      <PageTitle title="Jurnal">
        Aici se vede tot ce a făcut programul, pas cu pas. Este de folos când ceva nu merge și cereți ajutor.
      </PageTitle>

      {operation ? (
        <Notice tone="fresh" className="items-center">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2.5">
            <p className="min-w-0 flex-[1_1_320px] font-semibold">
              Se arată o singură operațiune, de la primul pas la ultimul.
            </p>
            {/* autoFocus: the link that opened this view is gone with the list it was in. */}
            <Button autoFocus variant="outline" onClick={() => setOperation(null)}>Înapoi la tot jurnalul</Button>
          </div>
        </Notice>
      ) : (
        <JournalFilters choice={choice} onChange={setChoice} />
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button variant="outline" onClick={() => { journal.refetch(); if (withRecords) records.refetch() }} disabled={reading}>
          {reading ? 'Se citește…' : 'Citește din nou'}
        </Button>
        <Button asChild variant="outline">
          <a href={api.journalFileAddress(filter)} download>Descarcă jurnalul</a>
        </Button>
        <div className="flex min-h-12 items-center gap-2.5">
          <Switch id="journal-technical" checked={technical} onCheckedChange={setTechnical} />
          <Label htmlFor="journal-technical">Vizualizare tehnică</Label>
        </div>
        {technical && (
          <p className="min-w-0 flex-[1_1_320px] text-[0.94rem] text-muted-foreground">
            Arată cererile către ANAF și Jev, ce s-a trimis, ce s-a primit și jurnalul programului.
            {!operation && ' Le găsiți deschizând un rând și operațiunea lui.'}
          </p>
        )}
      </div>

      {withRecords && records.error && <ErrorNotice error={records.error} />}
      {withRecords && records.data && (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-2xl border bg-card px-4.5 py-3.5">
          <span className="font-mono text-[0.9rem]">operațiunea {operation}</span>
          {summary ? (
            <>
              {summary.requests && <span className="font-semibold">{summary.requests}</span>}
              {summary.problems && <span className="font-semibold text-destructive">{summary.problems}</span>}
              {summary.records && <span>{summary.records}</span>}
              <span className="text-muted-foreground">de la {summary.from} la {summary.to}</span>
            </>
          ) : (
            <span className="text-muted-foreground">Nu are cereri către ANAF sau Jev și nici rânduri din program.</span>
          )}
        </div>
      )}

      {journal.error && <ErrorNotice error={journal.error} />}
      {/* A reading that failed does not take away the lines already read: they stay under the notice. */}
      {(!journal.error || lines.length > 0) && (
        <section aria-label="Jurnal" className="overflow-hidden rounded-2xl border bg-card">
          {journal.isPending && <p role="status" className="px-5 py-6 text-lg text-muted-foreground">Se încarcă jurnalul…</p>}
          {!journal.isPending && items.length === 0 && (
            <p className="px-5 py-6 text-lg">
              Nimic de arătat. Încercați altă perioadă, altă zonă sau alt cuvânt căutat.
              {!operation && !filter.details && ' Detaliile se văd numai dacă bifați „Arată și detaliile”.'}
            </p>
          )}
          {operation && older}
          {groupByDay(items).map(([day, ofTheDay]) => (
            <div key={day}>
              <h2 className="bg-background px-4.5 py-2.5 font-sans text-base font-bold">{day === today() ? 'Azi, ' : ''}{formatDate(day)}</h2>
              {ofTheDay.map((item) =>
                item.kind === 'line' ? (
                  <JournalEntry
                    key={`line-${item.line.id}`}
                    line={item.line}
                    onShowOperation={operation ? undefined : setOperation}
                    technical={technical}
                    counts={item.line.trace ? counts[item.line.trace] : undefined}
                  />
                ) : (
                  <TechnicalEntry key={`record-${item.record.id}`} record={item.record} />
                ),
              )}
            </div>
          ))}
          {!operation && older}
        </section>
      )}
      <p className="text-[0.94rem] text-muted-foreground">
        {technical
          ? 'Jurnalul păstrează ultimele 30 de zile, iar partea tehnică ultimele 7. Cheile, parolele și tokenurile sunt ascunse, ' +
            'iar fișierele descărcate de la ANAF nu se păstrează, doar mărimea lor. Nimic nu pleacă de pe acest calculator.'
          : 'Jurnalul păstrează ultimele 30 de zile. Cheile și parolele nu se scriu niciodată în el.'}
      </p>
    </div>
  )
}

/** Steps and records under the day they happened on, keeping their order. */
function groupByDay(items: TimelineItem[]): [string, TimelineItem[]][] {
  const days = new Map<string, TimelineItem[]>()
  for (const item of items) {
    const day = (item.kind === 'line' ? item.line.at : item.record.at).slice(0, 10)
    days.set(day, [...(days.get(day) ?? []), item])
  }
  return [...days]
}
