import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useRef } from 'react'
import { Notice } from '@/components/Notice'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { api } from '../api'
import { errorMessage } from '../errorMessages'
import { countOf } from '../format'
import type { ImportResult } from '../types'

// Why a row of the file was skipped, as the program names it.
const WHY_SKIPPED: Record<string, (cui: string) => string> = {
  invalid_cui: (cui) => `CUI ${cui} nu este corect. Verificați dacă a fost scris bine în fișier.`,
  missing_cui: () => 'lipsește CUI-ul.',
  missing_name: () => 'lipsește numele clientului.',
}

/** Adding many clients at once from the accountant's own Excel or CSV list. */
export function ImportClientsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient()
  const filePicker = useRef<HTMLInputElement>(null)
  const upload = useMutation({
    mutationFn: api.importClients,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['clients'] }),
  })
  const close = () => {
    upload.reset()
    onClose()
  }

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && close()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-heading text-3xl">Importă clienți din Excel</DialogTitle>
          <DialogDescription className="text-lg">
            Fișierul trebuie să aibă două coloane: numele clientului și CUI-ul.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-wrap items-center gap-x-5 gap-y-3.5 rounded-xl border-2 border-dashed border-input p-5">
          <input
            ref={filePicker}
            type="file"
            accept=".xlsx,.csv"
            className="sr-only"
            tabIndex={-1} // the button beside it opens it; an invisible field must not take focus
            aria-label="Fișierul cu clienți"
            onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) upload.mutate(file)
              event.target.value = '' // so the same file can be chosen again
            }}
          />
          <Button size="lg" disabled={upload.isPending} onClick={() => filePicker.current?.click()}>
            Alege fișierul
          </Button>
          <div className="min-w-0 flex-[1_1_240px]">
            <div className="font-semibold">{upload.variables?.name ?? 'Niciun fișier ales'}</div>
            <div className="text-muted-foreground">
              {upload.data ? `${countOf(upload.data.rows, 'un rând citit', 'rânduri citite')}` : 'Excel (.xlsx) sau CSV'}
            </div>
          </div>
        </div>

        {upload.error && <Notice tone="attention">{errorMessage(upload.error)}</Notice>}
        {upload.data && <ImportOutcome result={upload.data} />}

        <DialogFooter>
          <Button variant="secondary" size="lg" onClick={close}>Gata</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ImportOutcome({ result }: { result: ImportResult }) {
  const nothingChanged = !result.added.length && !result.updated.length && !result.rejected.length
  return (
    <div className="flex flex-col gap-2.5">
      {result.added.length > 0 && (
        <Notice tone="done">
          <span className="font-semibold">{countOf(result.added.length, 'Un client adăugat', 'clienți adăugați')}</span>
        </Notice>
      )}
      {result.updated.length > 0 && (
        <Notice tone="fresh">
          <span className="font-semibold">
            {countOf(result.updated.length, 'Un client exista deja; i-am actualizat numele', 'clienți existau deja; le-am actualizat numele')}
          </span>
        </Notice>
      )}
      {nothingChanged && <Notice tone="fresh">Toți clienții din fișier erau deja în listă.</Notice>}
      {result.rejected.length > 0 && (
        <Notice tone="attention">
          <p className="font-bold">
            {countOf(result.rejected.length, 'Un rând nu a fost importat', 'rânduri nu au fost importate')}
          </p>
          <ul className="mt-1 flex flex-col gap-1">
            {result.rejected.map((row) => (
              <li key={row.row}>
                Rândul {row.row}{row.name && `, „${row.name}”`}: {(WHY_SKIPPED[row.code] ?? (() => 'nu a putut fi citit.'))(row.cui)}
              </li>
            ))}
          </ul>
        </Notice>
      )}
    </div>
  )
}
