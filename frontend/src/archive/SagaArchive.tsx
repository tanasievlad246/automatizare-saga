import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Notice } from '@/components/Notice'
import { Pager } from '@/components/Pager'
import { pageOf, rangeLine } from '@/components/paging'
import { api } from '../api'
import { errorMessage } from '../errorMessages'
import { ARCHIVE_TEXT } from './archiveTexts'
import { ImportCard } from './ImportCard'

const IMPORTS_PER_PAGE = 20
const IMPORT_NOUN = { one: 'Importul', many: 'Importurile' }

/**
 * The "Arhivă" tab of a client's screen: every import in SAGA confirmed, by the automation
 * or on screen, the newest first. `openImport` is the one to show opened, from an invoice's link
 * or from the address; opening or closing one says so through `onOpenImport`.
 */
export function SagaArchive({ cui, openImport, onOpenImport }: {
  cui: string
  openImport: string | null
  onOpenImport: (id: number | null) => void
}) {
  const { data, error, isPending } = useQuery({ queryKey: ['saga-archive', cui], queryFn: () => api.sagaArchive(cui) })
  const imports = data?.imports ?? []
  // The page that holds the import asked for, when there is one.
  const wanted = imports.findIndex((entry) => String(entry.id) === openImport)
  const [chosenPage, setChosenPage] = useState<number | null>(null)
  const page = pageOf(imports, chosenPage ?? (wanted >= 0 ? Math.floor(wanted / IMPORTS_PER_PAGE) + 1 : 1), IMPORTS_PER_PAGE)

  return (
    <section aria-labelledby="archive-title" className="flex flex-col gap-4">
      <h2 id="archive-title" className="sr-only">Arhiva importurilor în SAGA</h2>
      <p className="text-muted-foreground">{ARCHIVE_TEXT.intro}</p>
      {error && <Notice tone="attention">{errorMessage(error)}</Notice>}
      {isPending ? (
        <p className="text-muted-foreground">Se încarcă arhiva…</p>
      ) : !error && imports.length === 0 ? (
        <div role="status" className="rounded-2xl border bg-card px-6 py-5.5">
          <p className="text-lg font-semibold">{ARCHIVE_TEXT.emptyTitle}</p>
          <p className="text-muted-foreground">{ARCHIVE_TEXT.emptyText}</p>
        </div>
      ) : (
        <ol aria-label="Importurile" className="flex flex-col gap-3.5">
          {page.items.map((entry) => (
            <ImportCard
              key={entry.id}
              entry={entry}
              cui={cui}
              startOpen={String(entry.id) === openImport}
              onToggle={(open) => onOpenImport(open ? entry.id : String(entry.id) === openImport ? null : Number(openImport) || null)}
            />
          ))}
        </ol>
      )}
      <Pager page={page} label="Paginile arhivei" line={rangeLine(page, IMPORT_NOUN)} onPage={setChosenPage} />
      <p className="text-[0.9rem] text-muted-foreground">{ARCHIVE_TEXT.older}</p>
    </section>
  )
}
