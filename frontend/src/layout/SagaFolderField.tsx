import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api } from '../api'
import { showError } from '../errorMessages'

/** Where the files for SAGA are written: shown on every screen, changed by picking or typing. */
export function SagaFolderField() {
  const queryClient = useQueryClient()
  const saved = useQuery({ queryKey: ['saga-folder'], queryFn: api.sagaFolder }).data?.saga_folder ?? ''
  const [typed, setTyped] = useState(saved)
  useEffect(() => setTyped(saved), [saved])

  const save = useMutation({
    mutationFn: api.setSagaFolder,
    onSuccess: (reply) => {
      queryClient.setQueryData(['saga-folder'], reply)
      toast.success('Folderul pentru SAGA a fost schimbat.')
    },
    onError: showError,
  })
  // A web page is never told a folder's path, so the program opens the computer's own dialog.
  const choose = useMutation({
    mutationFn: api.chooseFolder,
    onSuccess: ({ folder }) => folder && save.mutate(folder),
    onError: showError,
  })

  return (
    <form
      className="flex min-w-0 flex-[1_1_440px] flex-wrap items-center gap-2.5"
      onSubmit={(event) => {
        event.preventDefault()
        save.mutate(typed)
      }}
    >
      <Label htmlFor="saga-folder">Folderul pentru SAGA</Label>
      <Input
        id="saga-folder"
        value={typed}
        onChange={(event) => setTyped(event.target.value)}
        className="h-11 min-w-0 flex-[1_1_200px]"
      />
      {typed.trim() !== saved ? (
        <Button type="submit" size="sm" disabled={save.isPending}>Salvează</Button>
      ) : (
        <Button type="button" variant="outline" size="sm" disabled={choose.isPending} onClick={() => choose.mutate()}>
          {choose.isPending ? 'Alegeți în fereastra deschisă…' : 'Alege folderul'}
        </Button>
      )}
    </form>
  )
}
