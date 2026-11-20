import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { Notice } from '@/components/Notice'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { api } from '../api'
import { importedLine } from '../archive/archiveTexts'
import { COPY_REFUSED, copyText } from '../clipboard'
import { showError } from '../errorMessages'
import type { Invoice, SagaState } from '../types'
import { opensWindowsHere, pathOnThisPC, useWhere } from '../where'
import { fileCardNote } from './sagaFiles'

/** Which file for SAGA the invoice is in, if any, and whether it has been imported there. */
export function SagaFileCard({ invoice, saga }: { invoice: Invoice; saga: SagaState }) {
  const queryClient = useQueryClient()
  const setImported = useMutation({
    mutationFn: (imported: boolean) => api.markUploaded([invoice.id], imported),
    onSuccess: () => {
      for (const key of ['invoice', 'invoices', 'clients', 'saga-archive']) queryClient.invalidateQueries({ queryKey: [key] })
    },
    onError: showError,
  })
  const openFolder = useMutation({ mutationFn: () => api.openFolderOf(invoice.id), onError: showError })
  const where = useWhere()
  const note = fileCardNote(invoice, saga)
  // While the client's folder is not up to date, the file may not say what this screen says.
  const stale = saga.problem !== null || !saga.up_to_date
  // As this computer reaches it: through the shared folder when the program runs on the NAS.
  const path = stale || !invoice.saga_xml_path ? null : pathOnThisPC(invoice.saga_xml_path, where)
  const copyPath = () =>
    copyText(path ?? '').then(
      () => toast.success('Calea a fost copiată.'),
      () => toast.error('Calea nu a fost copiată.', { description: COPY_REFUSED, duration: Infinity }),
    )

  return (
    <section aria-label="Fișierul pentru SAGA" className="flex flex-col gap-3 rounded-2xl border bg-card px-5 pt-4.5 pb-5.5">
      <h2 className="font-sans text-xl font-bold">Fișierul pentru SAGA</h2>
      {note && (stale ? <Notice tone="attention">{note}</Notice> : <p className="text-muted-foreground">{note}</p>)}
      {path && (
        <>
          <p className="rounded-lg bg-background px-3.5 py-3 font-mono text-[0.88rem] break-all">{path}</p>
          <div className="flex flex-wrap gap-2.5">
            <Button variant="outline" onClick={copyPath}>Copiază calea</Button>
            {opensWindowsHere(where) && (
              <Button variant="outline" disabled={openFolder.isPending} onClick={() => openFolder.mutate()}>
                Deschide folderul
              </Button>
            )}
          </div>
        </>
      )}
      <div className="flex min-h-12 items-center gap-3">
        <Checkbox
          id="imported-in-saga"
          checked={invoice.uploaded_to_accounting}
          // Not ticked while the folder is not up to date: SAGA may never have got this invoice.
          disabled={setImported.isPending || (stale && !invoice.uploaded_to_accounting)}
          onCheckedChange={(checked) => setImported.mutate(checked === true)}
        />
        <Label htmlFor="imported-in-saga">Am importat factura în SAGA</Label>
      </div>
      {/* Imported with a confirmed import: when, by whom, and the way to it in the client's archive.
          Not when it was ticked again by hand since: then that import is not how it went to SAGA. */}
      {invoice.uploaded_to_accounting && invoice.saga_import && invoice.uploaded_at === invoice.saga_import.imported_at && (
        <p>
          {importedLine(invoice.saga_import)}{' '}
          <Link to={`/clienti/${invoice.cui}?fel=arhiva&import=${invoice.saga_import.id}`} className="font-semibold">
            Vezi importul în arhivă
          </Link>
        </p>
      )}
    </section>
  )
}
