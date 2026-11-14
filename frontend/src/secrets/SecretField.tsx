import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { api } from '../api'
import { showError } from '../errorMessages'
import type { Secret } from '../types'

const HIDDEN = '•'.repeat(20)

/** One key: hidden until asked for, and changeable when the program allows it. */
export function SecretField({ secret, name }: { secret: Secret; name: string }) {
  const queryClient = useQueryClient()
  const [shown, setShown] = useState(false)
  const [typed, setTyped] = useState<string | null>(null) // null: not being changed
  const save = useMutation({
    mutationFn: () => api.setSecret(secret.key, typed ?? ''),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['secrets'] })
      setTyped(null)
      toast.success('Cheia a fost salvată.')
    },
    onError: showError,
  })

  return (
    <div className="flex flex-col gap-2.5 rounded-2xl border bg-card px-5 py-4.5">
      <div className="text-lg font-bold">{name}</div>
      {typed === null ? (
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex min-h-12 min-w-0 flex-[1_1_280px] items-center rounded-lg bg-background px-3.5 font-mono text-[0.94rem] break-all">
            {secret.value ? (shown ? secret.value : HIDDEN) : <span className="font-sans text-muted-foreground">necompletată</span>}
          </div>
          <Button
            variant={shown ? 'secondary' : 'outline'}
            className="min-w-28"
            disabled={!secret.value}
            aria-pressed={shown}
            onClick={() => setShown(!shown)}
          >
            {shown ? 'Ascunde' : 'Arată'}
          </Button>
          {secret.editable && <Button variant="outline" onClick={() => setTyped(secret.value)}>Modifică</Button>}
        </div>
      ) : (
        <form
          className="flex flex-wrap items-center gap-2.5"
          onSubmit={(event) => {
            event.preventDefault()
            save.mutate()
          }}
        >
          <Input
            aria-label={name}
            autoFocus
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            className="min-w-0 flex-[1_1_280px] font-mono"
          />
          <Button type="submit" disabled={save.isPending}>Salvează</Button>
          <Button type="button" variant="outline" onClick={() => setTyped(null)}>Renunță</Button>
        </form>
      )}
      {!secret.editable && <p className="text-muted-foreground">Se poate doar citi aici.</p>}
    </div>
  )
}
