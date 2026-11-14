import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { api } from '../api'
import { showError } from '../errorMessages'
import type { Invoice } from '../types'

/** Where the file for SAGA is, and whether the invoice has been imported there. */
export function SagaFileCard({ invoice }: { invoice: Invoice }) {
  const queryClient = useQueryClient()
  const setImported = useMutation({
    mutationFn: (imported: boolean) => api.markUploaded([invoice.id], imported),
    onSuccess: () => {
      for (const key of ['invoice', 'invoices', 'clients']) queryClient.invalidateQueries({ queryKey: [key] })
    },
    onError: showError,
  })
  const openFolder = useMutation({ mutationFn: () => api.openFolderOf(invoice.id), onError: showError })
  const path = invoice.saga_xml_path
  const copyPath = () =>
    navigator.clipboard.writeText(path ?? '').then(() => toast.success('Calea a fost copiată.'), showError)

  return (
    <section aria-label="Fișierul pentru SAGA" className="flex flex-col gap-3 rounded-2xl border bg-card px-5 pt-4.5 pb-5.5">
      <h2 className="font-sans text-xl font-bold">Fișierul pentru SAGA</h2>
      {path ? (
        <>
          <p className="rounded-lg bg-background px-3.5 py-3 font-mono text-[0.88rem] break-all">{path}</p>
          <div className="flex flex-wrap gap-2.5">
            <Button variant="outline" onClick={copyPath}>Copiază calea</Button>
            <Button variant="outline" disabled={openFolder.isPending} onClick={() => openFolder.mutate()}>
              Deschide folderul
            </Button>
          </div>
        </>
      ) : (
        <p className="text-muted-foreground">Se creează imediat ce factura are un cont.</p>
      )}
      <div className="flex min-h-12 items-center gap-3">
        <Checkbox
          id="imported-in-saga"
          checked={invoice.uploaded_to_accounting}
          disabled={setImported.isPending}
          onCheckedChange={(checked) => setImported.mutate(checked === true)}
        />
        <Label htmlFor="imported-in-saga">Am importat factura în SAGA</Label>
      </div>
    </section>
  )
}
