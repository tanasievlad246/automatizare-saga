import { keepPreviousData, useInfiniteQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { ErrorNotice } from '@/components/ErrorNotice'
import { Notice } from '@/components/Notice'
import { PageTitle } from '@/components/PageTitle'
import { Button } from '@/components/ui/button'
import { api } from '../api'
import type { JournalFilter } from '../api'
import { formatDate, today } from '../format'
import type { JournalLine } from '../types'
import { JournalEntry } from './JournalEntry'
import { JournalFilters } from './JournalFilters'
import type { JournalChoice } from './JournalFilters'
import { filterFor } from './journalFilter'

const EVERYTHING: JournalChoice = { shown: 'tot', details: false, area: '', period: 'azi', text: '' }

/** What the program did, newest first. One operation can be shown whole, in the order it happened. */
export function JournalPage() {
  const [choice, setChoice] = useState(EVERYTHING)
  const [operation, setOperation] = useState<string | null>(null) // the trace being looked at, if any

  const filter: JournalFilter = operation ? { trace: operation } : filterFor(choice)
  const journal = useInfiniteQuery({
    queryKey: ['journal', filter],
    queryFn: ({ pageParam }) => api.journal(filter, pageParam),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (last) => (last.has_more ? last.events.at(-1)?.id : undefined),
    placeholderData: keepPreviousData, // the list stays while the next answer is on its way
    refetchOnWindowFocus: true,
  })
  const lines = journal.data?.pages.flatMap((page) => page.events) ?? []
  // One operation is read from its first step to its last; everything else newest first.
  const inOrder = operation ? [...lines].reverse() : lines
  // Older lines are read on request. In one operation they are its earlier steps, which
  // come in at the top, so the button is above the list there, and below it everywhere else.
  const older = journal.hasNextPage && (
    <div className={operation ? 'px-4.5 py-3.5' : 'border-t px-4.5 py-3.5'}>
      <Button variant="outline" disabled={journal.isFetchingNextPage} onClick={() => journal.fetchNextPage()}>
        {journal.isFetchingNextPage ? 'Se încarcă…' : operation ? 'Arată pașii de dinainte' : 'Arată mai vechi'}
      </Button>
    </div>
  )

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
        <Button variant="outline" onClick={() => journal.refetch()} disabled={journal.isFetching}>
          {journal.isFetching ? 'Se citește…' : 'Citește din nou'}
        </Button>
        <Button asChild variant="outline">
          <a href={api.journalFileAddress(filter)} download>Descarcă jurnalul</a>
        </Button>
      </div>

      {journal.error && <ErrorNotice error={journal.error} />}
      {/* A reading that failed does not take away the lines already read: they stay under the notice. */}
      {(!journal.error || lines.length > 0) && (
        <section aria-label="Jurnal" className="overflow-hidden rounded-2xl border bg-card">
          {journal.isPending && <p role="status" className="px-5 py-6 text-lg text-muted-foreground">Se încarcă jurnalul…</p>}
          {!journal.isPending && lines.length === 0 && (
            <p className="px-5 py-6 text-lg">
              Nimic de arătat. Încercați altă perioadă, altă zonă sau alt cuvânt căutat.
              {!operation && !filter.details && ' Detaliile se văd numai dacă bifați „Arată și detaliile”.'}
            </p>
          )}
          {operation && older}
          {groupByDay(inOrder).map(([day, ofTheDay]) => (
            <div key={day}>
              <h2 className="bg-background px-4.5 py-2.5 font-sans text-base font-bold">{day === today() ? 'Azi, ' : ''}{formatDate(day)}</h2>
              {ofTheDay.map((line) => (
                <JournalEntry key={line.id} line={line} onShowOperation={operation ? undefined : setOperation} />
              ))}
            </div>
          ))}
          {!operation && older}
        </section>
      )}
      <p className="text-[0.94rem] text-muted-foreground">
        Jurnalul păstrează ultimele 30 de zile. Cheile și parolele nu se scriu niciodată în el.
      </p>
    </div>
  )
}

/** Lines under the day they were written on, keeping their order. */
function groupByDay(lines: JournalLine[]): [string, JournalLine[]][] {
  const days = new Map<string, JournalLine[]>()
  for (const line of lines) {
    const day = line.at.slice(0, 10)
    days.set(day, [...(days.get(day) ?? []), line])
  }
  return [...days]
}
