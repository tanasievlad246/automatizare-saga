import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { toast } from 'sonner'
import { ErrorNotice } from '@/components/ErrorNotice'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api } from '../api'

/** Changing the folder the files for SAGA are written to: picked in Windows' own dialog, or typed. */
export function SagaFolderDialog({ saved, onClose }: { saved: string; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [typed, setTyped] = useState(saved)
  const save = useMutation({
    mutationFn: () => api.setSagaFolder(typed.trim()),
    onSuccess: (reply) => {
      queryClient.setQueryData(['saga-folder'], reply)
      toast.success('Folderul pentru SAGA a fost schimbat. Fișierele create până acum rămân în folderul vechi.')
      onClose()
    },
  })
  // A web page is never told a folder's path, so the program opens the computer's own dialog.
  const choose = useMutation({
    mutationFn: api.chooseFolder,
    onSuccess: ({ folder }) => folder && setTyped(folder),
  })
  const failure = save.error ?? choose.error
  const changed = typed.trim() !== '' && typed.trim() !== saved

  return (
    <Dialog open onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-heading text-3xl">Folderul pentru SAGA</DialogTitle>
          <DialogDescription className="text-lg">
            Aici scrie programul fișierele pe care le importați în SAGA. Fiecare client are folderul lui.
          </DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
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
