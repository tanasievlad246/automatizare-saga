import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Notice } from '@/components/Notice'
import { Button } from '@/components/ui/button'
import { api } from '../api'
import { showError } from '../errorMessages'
import { formatWhen } from '../format'
import { goesToSales, kindsLine } from './issuedInvoices'
import type { Invoice, SagaState } from '../types'
import { importedButton, isStale, NOT_UP_TO_DATE, placeLine, readyPlaces } from './sagaFiles'

/**
 * What waits for SAGA, and the answer after importing it: the client's one file (or the
 * folder with a file per invoice), then one button that marks every ready invoice as imported.
 */
export function ImportedInSagaCard({ cui, ready, saga }: { cui: string; ready: Invoice[]; saga: SagaState | undefined }) {
  const queryClient = useQueryClient()
  const refresh = () => {
    for (const key of ['invoices', 'invoice', 'clients']) queryClient.invalidateQueries({ queryKey: [key] })
  }
  const markImported = useMutation({
    mutationFn: () => api.markUploaded(ready.map((invoice) => invoice.id)),
    onSuccess: () => {
      refresh()
      toast.success('Facturile au fost marcate ca importate în SAGA.')
    },
    onError: showError,
  })
  const tryAgain = useMutation({
    mutationFn: () => api.writeSagaFiles(cui),
    onSuccess: ({ problems }) => {
      refresh()
      if (problems.length === 0) toast.success('Folderul pentru SAGA este la zi.')
      else toast.error(NOT_UP_TO_DATE.still)
    },
    onError: showError,
  })
  const openFolder = useMutation({ mutationFn: api.openFolderOf, onError: showError })

  if (!saga) return null
  const stale = isStale(ready, saga)
  if (ready.length === 0 && !stale) return null
  const copyPath = (path: string) =>
    navigator.clipboard.writeText(path).then(() => toast.success('Calea a fost copiată.'), showError)

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
              <p className="rounded-lg bg-background px-3.5 py-3 font-mono text-[0.88rem] break-all">{path}</p>
              {kindsOf(invoices) && <p>{kindsOf(invoices)}</p>}
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2.5">
                <Button variant="outline" size="sm" disabled={openFolder.isPending} onClick={() => openFolder.mutate(invoices[0].id)}>
                  Deschide folderul
                </Button>
                <Button variant="outline" size="sm" onClick={() => copyPath(path)}>Copiază calea</Button>
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
      {ready.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-3 border-t pt-3">
          <p className="min-w-0 flex-[1_1_320px] text-muted-foreground">
            {stale
              ? NOT_UP_TO_DATE.first
              : saga.file_per === 'client'
                ? 'După ce importați fișierul în SAGA, apăsați butonul. Fișierul dispare din folder până apar facturi noi.'
                : 'După ce le importați în SAGA, apăsați butonul. Fișierele lor dispar din folder.'}
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
