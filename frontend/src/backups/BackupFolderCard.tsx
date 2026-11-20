import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { toast } from 'sonner'
import { ErrorNotice } from '@/components/ErrorNotice'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api } from '../api'
import { opensWindowsHere, typeTheFolder, useWhere } from '../where'

/** Where the copies are kept: picked in Windows' own dialog, or typed. */
export function BackupFolderCard({ saved }: { saved: string }) {
  const queryClient = useQueryClient()
  const [typed, setTyped] = useState(saved)
  const save = useMutation({
    mutationFn: () => api.setBackupFolder(typed.trim()),
    onSuccess: (status) => {
      queryClient.setQueryData(['backups'], status)
      toast.success('Folderul copiilor de siguranță a fost salvat.')
    },
  })
  // A web page is never told a folder's path, so the program opens the computer's own dialog.
  // Told what the folder is for, so the dialog is titled for the copies and opens where they are.
  const choose = useMutation({ mutationFn: () => api.chooseFolder('backups'), onSuccess: ({ folder }) => folder && setTyped(folder) })
  const failure = save.error ?? choose.error
  const changed = typed.trim() !== '' && typed.trim() !== saved
  const here = opensWindowsHere(useWhere())

  return (
    <section aria-label="Folderul copiilor" className="flex flex-col gap-3 rounded-2xl border bg-card px-5 py-4.5">
      <h2 className="font-sans text-xl font-bold">Unde se păstrează copiile</h2>
      <form
        className="flex flex-wrap gap-2.5"
        onSubmit={(event) => {
          event.preventDefault()
          if (changed) save.mutate()
        }}
      >
        <Label htmlFor="backup-folder" className="sr-only">Folderul copiilor</Label>
        <Input id="backup-folder" className="min-w-0 flex-[1_1_320px]" placeholder="de exemplu E:\Copii AutoSaga" value={typed} onChange={(event) => setTyped(event.target.value)} />
        {here && <Button type="button" variant="outline" disabled={choose.isPending} onClick={() => choose.mutate()}>Alege folderul</Button>}
        <Button type="submit" disabled={!changed || save.isPending}>Salvează</Button>
      </form>
      {!here && <p className="text-[0.95rem] text-muted-foreground">{typeTheFolder('/backups')}</p>}
      {choose.isPending && (
        <p role="status" className="text-[0.95rem] text-muted-foreground">
          Alegeți folderul în fereastra deschisă. Dacă nu o vedeți, este în spatele acestei pagini.
        </p>
      )}
      {failure && <ErrorNotice error={failure} />}
      <p className="text-[0.95rem] text-muted-foreground">
        Alegeți un loc care nu este pe același disc cu programul: un stick USB, alt disc sau un folder care se copiază
        singur pe internet. O copie ținută pe același disc nu ajută dacă discul se strică.
      </p>
      <p className="text-[0.95rem] text-muted-foreground">
        O copie conține clienții, facturile, conturile, regulile și setările, inclusiv cheile schimbate pe pagina „Chei
        și parole”. Conectarea la ANAF nu este în copie. Țineți folderul doar pentru dumneavoastră.
      </p>
    </section>
  )
}
