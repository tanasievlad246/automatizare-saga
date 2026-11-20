import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { Notice } from '@/components/Notice'
import { Button } from '@/components/ui/button'
import { ApiError, api } from '../api'
import { CHANGED_MEANWHILE, confirmedToast } from '../archive/archiveTexts'
import { COPY_REFUSED, copyText } from '../clipboard'
import { showError } from '../errorMessages'
import { fileNameOf, formatWhen } from '../format'
import { DownloadFileButton } from '../sagaFiles/DownloadFileButton'
import type { SeenOf } from '../sagaFiles/useSeenFiles'
import { goesToSales, kindsLine } from './issuedInvoices'
import type { Invoice, SagaState } from '../types'
import { opensWindowsHere, pathOnThisPC, useWhere } from '../where'
import { importedButton, isStale, NOT_UP_TO_DATE, placeLine, readyPlaces } from './sagaFiles'

/**
 * What waits for SAGA, and the answer after importing it: the client's one file (or the
 * folder with a file per invoice), then one button that marks every invoice in it as imported
 * and moves the file to the archive. The version of the files as the person saw them goes with
 * it: if they have changed since (a download added an invoice, even one the page then
 * reloaded by itself), nothing is marked and the card says so. `seen`: what the person has seen
 * of all the client's files together, kept by the client's screen (useSeenFiles); it is taken
 * again when they open the folder, copy the path or save the file, about to import it.
 * `onShowFiles`: beside the path, a way to the "Fișiere pentru SAGA" tab, where what the file
 * holds is seen; called as it is taken. `fileHasItsOwnButton`: the card is under that tab and the
 * client's one file has „Fișier importat” on it, which does the same; then only the notice that
 * the folder is not up to date is shown here. `onWritten`: the files were written again.
 * `onDownloaded`: the client's file was saved, in that version.
 */
export function ImportedInSagaCard({
  cui, ready, saga, seen, fileHasItsOwnButton = false, onShowFiles, onWritten, onDownloaded,
}: {
  cui: string
  ready: Invoice[]
  saga: SagaState | undefined
  seen: SeenOf
  fileHasItsOwnButton?: boolean
  onShowFiles?: () => void
  onWritten: () => void
  onDownloaded: (name: string, version: string | null) => void
}) {
  const queryClient = useQueryClient()
  const refresh = () => {
    for (const key of ['invoices', 'invoice', 'clients', 'saga-archive']) queryClient.invalidateQueries({ queryKey: [key] })
  }
  const current = saga?.version ?? null
  const markImported = useMutation({
    // With nothing kept as seen (just confirmed, or refused), what the page lists now is sent.
    mutationFn: () => api.confirmSagaImport(cui, seen.version ?? current),
    onMutate: seen.attempt,
    onSuccess: ({ archive }) => {
      seen.confirmed()
      refresh()
      toast.success(archive ? confirmedToast(archive.invoices, archive.files.length) : 'Nu mai era nicio factură în fișier.')
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === 'saga_files_changed') {
        // Shown here, beside the file, which the refresh brings as it is now: what the person
        // sees next is that file, so its version is the one a second press sends.
        seen.refused()
        refresh()
      } else {
        // A file gone from the folder: the refresh brings the notice with „Încearcă din nou”.
        if (error instanceof ApiError && error.code === 'saga_files_stale') refresh()
        showError(error)
      }
    },
  })
  const tryAgain = useMutation({
    mutationFn: () => api.writeSagaFiles(cui),
    onSuccess: ({ problems }) => {
      onWritten() // the file was written again: what the person sees next is the new one
      refresh()
      if (problems.length === 0) toast.success('Folderul pentru SAGA este la zi.')
      else toast.error(NOT_UP_TO_DATE.still)
    },
    onError: showError,
  })
  const openFolder = useMutation({ mutationFn: api.openFolderOf, onError: showError })
  const where = useWhere()

  if (!saga) return null
  const stale = isStale(ready, saga)
  if (!stale && (ready.length === 0 || fileHasItsOwnButton)) return null
  const copyPath = (path: string) => {
    seen.look()
    copyText(path).then(
      () => toast.success('Calea a fost copiată.'),
      () => toast.error('Calea nu a fost copiată.', { description: COPY_REFUSED, duration: Infinity }),
    )
  }
  const showFolder = (invoiceId: string) => {
    seen.look()
    openFolder.mutate(invoiceId)
  }

  return (
    <section aria-label="Importul în SAGA" className="flex flex-col gap-3 rounded-2xl border bg-card px-5 py-4.5">
      {ready.length > 0 && <h2 className="font-sans text-lg font-bold">Ați importat facturile în SAGA?</h2>}
      {stale ? (
        <Notice tone="attention">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
            <div className="min-w-0 flex-[1_1_360px]">
              <p className="font-bold">{NOT_UP_TO_DATE.title}</p>
              <p>{NOT_UP_TO_DATE.text}</p>
              {saga.problem && (
                <p className="text-[0.9rem] [overflow-wrap:anywhere]">
                  Ultima încercare: {formatWhen(saga.problem.at)}. Detalii tehnice: {saga.problem.message}
                </p>
              )}
            </div>
            <Button disabled={tryAgain.isPending} onClick={() => tryAgain.mutate()}>{NOT_UP_TO_DATE.retry}</Button>
          </div>
        </Notice>
      ) : (
        // Shown only while it can be trusted: what is listed gets imported as it is.
        <ul className="flex flex-col gap-3">
          {readyPlaces(ready, saga.file_per).map(({ path, invoices }) => (
            <li key={path} className="flex flex-col gap-2.5">
              <p className="text-muted-foreground">{placeLine(invoices.length, saga.file_per)}</p>
              <p className="rounded-lg bg-background px-3.5 py-3 font-mono text-[0.88rem] break-all">{pathOnThisPC(path, where)}</p>
              {kindsOf(invoices) && <p>{kindsOf(invoices)}</p>}
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2.5">
                {opensWindowsHere(where) && (
                  <Button variant="outline" size="sm" disabled={openFolder.isPending} onClick={() => showFolder(invoices[0].id)}>
                    Deschide folderul
                  </Button>
                )}
                <Button variant="outline" size="sm" onClick={() => copyPath(pathOnThisPC(path, where))}>Copiază calea</Button>
                {/* Only where the path is a file: with a file for each invoice it is their folder. */}
                {saga.file_per === 'client' && (
                  <DownloadFileButton
                    cui={cui} name={fileNameOf(path)} size="sm"
                    onDownloaded={(version) => onDownloaded(fileNameOf(path), version)}
                  />
                )}
                {onShowFiles && (
                  <Link to={`/clienti/${cui}?fel=saga`} className="inline-flex min-h-11 items-center font-semibold" onClick={onShowFiles}>
                    {saga.file_per === 'client' ? 'Vezi ce este în fișier' : 'Vezi fișierele'}
                  </Link>
                )}
                {saga.file_per === 'client' && (
                  <span className="text-muted-foreground">
                    {saga.written_at && `Scris: ${formatWhen(saga.written_at)}. `}
                    Fișierul poartă numele primei facturi din el.
                  </span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {seen.changed && (
        <Notice tone="attention">
          <p className="font-bold">{CHANGED_MEANWHILE.title}</p>
          <p>{CHANGED_MEANWHILE.text}</p>
        </Notice>
      )}
      {ready.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-3 border-t pt-3">
          <p className="min-w-0 flex-[1_1_320px] text-muted-foreground">
            {stale
              ? NOT_UP_TO_DATE.first
              : saga.file_per === 'client'
                ? 'După ce importați fișierul în SAGA, apăsați butonul. Facturile se marchează ca importate, iar fișierul se mută în arhivă, la fila „Arhivă”.'
                : 'După ce le importați în SAGA, apăsați butonul. Facturile se marchează ca importate, iar fișierele lor se mută în arhivă, la fila „Arhivă”.'}
          </p>
          <Button
            variant="outline"
            size="lg"
            className="border-2 border-done-foreground font-bold text-done-foreground"
            disabled={markImported.isPending || stale}
            onClick={() => markImported.mutate()}
          >
            {importedButton(ready.length)}
          </Button>
        </div>
      )}
    </section>
  )
}

/** How many of these invoices SAGA puts among the purchases and how many among the sales. */
function kindsOf(invoices: Invoice[]): string | null {
  const sales = invoices.filter(goesToSales).length
  return kindsLine(invoices.length - sales, sales)
}
