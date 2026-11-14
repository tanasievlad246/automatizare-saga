import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { api } from '../api'
import { showError } from '../errorMessages'
import { countOf, folderOf } from '../format'
import type { Invoice } from '../types'

/** After importing into SAGA: one answer marks every ready invoice of this client as imported. */
export function ImportedInSagaCard({ ready }: { ready: Invoice[] }) {
  const queryClient = useQueryClient()
  const markImported = useMutation({
    mutationFn: () => api.markUploaded(ready.map((invoice) => invoice.id)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      queryClient.invalidateQueries({ queryKey: ['clients'] })
      toast.success('Facturile au fost marcate ca importate în SAGA.')
    },
    onError: showError,
  })
  const openFolder = useMutation({ mutationFn: api.openFolderOf, onError: showError })

  if (ready.length === 0) return null
  // Where the files really are. Normally one folder; more when the SAGA folder was changed
  // while some files were still waiting. Each is named, so none is forgotten at import.
  const folders = new Map<string, Invoice[]>()
  for (const invoice of ready) {
    const folder = folderOf(invoice.saga_xml_path ?? '')
    folders.set(folder, [...(folders.get(folder) ?? []), invoice])
  }

  return (
    <div className="flex flex-col gap-3 rounded-2xl border bg-card px-5 py-4.5">
      <p className="text-lg font-bold">Ați importat facturile în SAGA?</p>
      <ul className="flex flex-col gap-2">
        {[...folders].map(([folder, invoices]) => (
          <li key={folder} className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <span className="min-w-0 flex-[1_1_360px] text-muted-foreground">
              {countOf(invoices.length, 'O factură gata este', 'facturi gata sunt')} în folderul{' '}
              <span className="font-mono text-[0.9rem] break-all text-foreground">{folder}</span>
            </span>
            <Button variant="outline" size="sm" disabled={openFolder.isPending} onClick={() => openFolder.mutate(invoices[0].id)}>
              Deschide folderul
            </Button>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
        <p className="min-w-0 flex-[1_1_320px] text-muted-foreground">
          După ce le importați în SAGA{folders.size > 1 ? ', din toate folderele de mai sus' : ''}, apăsați butonul.
        </p>
        <Button
          variant="outline"
          size="lg"
          className="border-2 border-done-foreground font-bold text-done-foreground"
          disabled={markImported.isPending}
          onClick={() => markImported.mutate()}
        >
          Da, le-am importat în SAGA
        </Button>
      </div>
    </div>
  )
}
