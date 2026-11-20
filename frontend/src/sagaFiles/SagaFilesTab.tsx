import { useState } from 'react'
import { Notice } from '@/components/Notice'
import { Pager } from '@/components/Pager'
import { pageOf, rangeLine } from '@/components/paging'
import { errorMessage } from '../errorMessages'
import type { Invoice, WaitingFiles } from '../types'
import { WaitingFileCard } from './WaitingFileCard'
import { FILES_PER_PAGE, FILES_TAB, invoicesOf } from './waitingFiles'

const FILE_NOUN = { one: 'Fișierul', many: 'Fișierele' }

/**
 * The "Fișiere pentru SAGA" tab of a client's screen: every file in the client's folder that
 * still has to be imported, each with its invoices. `stale`: the folder may not hold what the
 * screen shows; the card under the tab has the button that brings it up to date.
 */
export function SagaFilesTab({
  cui, waiting, error, received, issued, stale,
}: {
  cui: string
  waiting: WaitingFiles | undefined
  error: unknown
  received: Invoice[] | undefined
  issued: Invoice[] | undefined
  stale: boolean
}) {
  const [wanted, setWanted] = useState(1)
  const files = waiting?.files ?? []
  const page = pageOf(files, wanted, FILES_PER_PAGE)

  return (
    <section aria-labelledby="saga-files-title" className="flex flex-col gap-4">
      <h2 id="saga-files-title" className="sr-only">Fișierele de importat în SAGA</h2>
      {files.length > 0 && <p className="text-muted-foreground">{FILES_TAB.intro}</p>}
      {error ? <Notice tone="attention">{errorMessage(error)}</Notice> : null}
      {stale && (
        <Notice tone="attention">
          <p className="font-bold">{FILES_TAB.staleTitle}</p>
          <p>{FILES_TAB.staleText}</p>
        </Notice>
      )}
      {!waiting && !error ? (
        <p role="status" className="text-muted-foreground">Se încarcă fișierele…</p>
      ) : files.length === 0 ? (
        // While the folder is not up to date, "none" is not known: the notice above says what to do.
        !error && !stale && (
          <div role="status" className="rounded-2xl border bg-card px-6 py-5.5">
            <p className="text-lg font-semibold">{FILES_TAB.emptyTitle}</p>
            <p className="text-muted-foreground">{FILES_TAB.emptyText}</p>
          </div>
        )
      ) : (
        <ol aria-label="Fișierele de importat" className="flex flex-col gap-3.5">
          {page.items.map((file) => (
            <WaitingFileCard key={file.path} cui={cui} file={file} invoices={invoicesOf(file.ids, received, issued)} />
          ))}
        </ol>
      )}
      <Pager page={page} label="Paginile fișierelor" line={rangeLine(page, FILE_NOUN)} onPage={setWanted} />
    </section>
  )
}
