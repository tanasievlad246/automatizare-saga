import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Notice } from '@/components/Notice'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { api } from '../api'
import { showError } from '../errorMessages'
import type { Invoice, SagaState } from '../types'
import { fileCardNote } from './sagaFiles'

/** Which file for SAGA the invoice is in, if any, and whether it has been imported there. */
export function SagaFileCard({ invoice, saga }: { invoice: Invoice; saga: SagaState }) {
  const queryClient = useQueryClient()
  const setImported = useMutation({
    mutationFn: (imported: boolean) => api.markUploaded([invoice.id], imported),
    onSuccess: () => {
      for (const key of ['invoice', 'invoices', 'clients']) queryClient.invalidateQueries({ queryKey: [key] })
    },
    onError: showError,
  })
  const openFolder = useMutation({ mutationFn: () => api.openFolderOf(invoice.id), onError: showError })
  const note = fileCardNote(invoice, saga)
  // While the client's folder is not up to date, the file may not say what this screen says.
  const stale = saga.problem !== null
  const path = stale ? null : invoice.saga_xml_path
  const copyPath = () =>
    navigator.clipboard.writeText(path ?? '').then(() => toast.success('Calea a fost copiată.'), showError)

  return (
    <section aria-label="Fișierul pentru SAGA" className="flex flex-col gap-3 rounded-2xl border bg-card px-5 pt-4.5 pb-5.5">
      <h2 className="font-sans text-xl font-bold">Fișierul pentru SAGA</h2>
      {note && (stale ? <Notice tone="attention">{note}</Notice> : <p className="text-muted-foreground">{note}</p>)}
      {path && (
        <>
          <p className="rounded-lg bg-background px-3.5 py-3 font-mono text-[0.88rem] break-all">{path}</p>
          <div className="flex flex-wrap gap-2.5">
            <Button variant="outline" onClick={copyPath}>Copiază calea</Button>
            <Button variant="outline" disabled={openFolder.isPending} onClick={() => openFolder.mutate()}>
              Deschide folderul
            </Button>
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
    </section>
  )
}
