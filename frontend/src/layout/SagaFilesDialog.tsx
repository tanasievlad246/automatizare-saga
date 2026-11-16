import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { toast } from 'sonner'
import { ErrorNotice } from '@/components/ErrorNotice'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { api } from '../api'
import { SAGA_WAYS } from '../invoices/sagaFiles'
import type { AppSettings, SagaFilePer } from '../types'

/**
 * The files for SAGA: the folder they are written to (picked in Windows' own dialog, or
 * typed) and whether a client gets one file for all its invoices or a file for each.
 */
export function SagaFilesDialog({ saved, onClose }: { saved: AppSettings; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [typed, setTyped] = useState(saved.saga_folder)
  const [way, setWay] = useState<SagaFilePer>(saved.saga_file_per)
  const folderChanged = typed.trim() !== '' && typed.trim() !== saved.saga_folder
  const wayChanged = way !== saved.saga_file_per
  const save = useMutation({
    // Only what was changed is sent: the rest stays as the program has it.
    mutationFn: () =>
      api.setSagaOutput({
        ...(folderChanged ? { saga_folder: typed.trim() } : {}),
        ...(wayChanged ? { saga_file_per: way } : {}),
      }),
    onSuccess: ({ problems, ...settings }) => {
      queryClient.setQueryData(['saga-folder'], settings)
      // Every waiting invoice may be in another file now.
      for (const key of ['invoices', 'invoice']) queryClient.invalidateQueries({ queryKey: [key] })
      if (problems.length === 0) toast.success('Fișierele pentru SAGA au fost scrise din nou.')
      else {
        toast.warning(
          'Am salvat ce ați ales, dar fișierele nu au putut fi scrise din nou pentru toți clienții. Lista de facturi a fiecărui client spune dacă folderul lui este la zi.',
        )
      }
      onClose()
    },
  })
  // A web page is never told a folder's path, so the program opens the computer's own dialog.
  const choose = useMutation({
    mutationFn: api.chooseFolder,
    onSuccess: ({ folder }) => folder && setTyped(folder),
  })
  const failure = save.error ?? choose.error
  const changed = typed.trim() !== '' && (folderChanged || wayChanged)

  return (
    <Dialog open onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-heading text-3xl">Fișierele pentru SAGA</DialogTitle>
          <DialogDescription className="text-lg">
            Unde scrie programul fișierele pe care le importați în SAGA și cum le împarte. Fiecare client are folderul lui.
          </DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-5"
          onSubmit={(event) => {
            event.preventDefault()
            if (changed) save.mutate()
          }}
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="saga-folder">Folderul</Label>
            <div className="flex flex-wrap gap-2.5">
              <Input id="saga-folder" className="min-w-0 flex-[1_1_280px]" value={typed} onChange={(event) => setTyped(event.target.value)} />
              <Button type="button" variant="outline" disabled={choose.isPending} onClick={() => choose.mutate()}>
                Alege folderul
              </Button>
            </div>
            {choose.isPending && (
              <p role="status" className="text-[0.95rem] text-muted-foreground">
                Alegeți folderul în fereastra deschisă. Dacă nu o vedeți, este în spatele acestei pagini.
              </p>
            )}
          </div>
          {/* Radio buttons: one way is always chosen, and never both. */}
          <fieldset className="flex flex-col gap-2.5">
            <legend className="mb-1.5 font-medium">Câte fișiere se scriu</legend>
            {SAGA_WAYS.map((each) => (
              <label
                key={each.value}
                className={cn(
                  'flex cursor-pointer gap-3 rounded-xl border-2 px-4 py-3.5 has-focus-visible:ring-3 has-focus-visible:ring-ring',
                  way === each.value ? 'border-primary bg-primary/5' : 'border-input',
                )}
              >
                <input
                  type="radio"
                  name="saga-files"
                  className="mt-1 size-5 shrink-0 accent-primary outline-none"
                  checked={way === each.value}
                  onChange={() => setWay(each.value)}
                />
                <span className="min-w-0">
                  <span className="block font-bold">{each.title}</span>
                  <span className="block text-muted-foreground">{each.text}</span>
                </span>
              </label>
            ))}
            <p className="text-muted-foreground">
              Oricum ați alege, în folder rămân doar facturile care nu sunt încă marcate ca importate în SAGA.
            </p>
          </fieldset>
          {failure && <ErrorNotice error={failure} />}
          <div className="flex flex-wrap gap-2.5">
            <Button type="submit" disabled={!changed || save.isPending}>Salvează</Button>
            <Button type="button" variant="outline" onClick={onClose}>Renunță</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
