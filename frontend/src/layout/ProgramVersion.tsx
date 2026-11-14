import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { api } from '../api'
import type { UpdateStatus } from '../types'
import { shownVersion } from './programUpdate'

/** At the foot of the menu: the version installed, and a way to look for a newer one now. */
export function ProgramVersion({ status }: { status: UpdateStatus }) {
  const queryClient = useQueryClient()
  const look = useMutation({
    mutationFn: () => api.updateStatus(true),
    // What it found is what the rest of the page shows, the notice on top included.
    onSuccess: (found) => queryClient.setQueryData(['program-update'], found),
  })
  const found = look.data

  return (
    <div className="mt-6 flex flex-col gap-1 px-3.5 text-[0.95rem]">
      <span className="text-muted-foreground">Versiunea {shownVersion(status.version)}</span>
      {status.can_update && (
        <Button variant="link" className="h-auto min-h-10 self-start px-0" disabled={look.isPending} onClick={() => look.mutate()}>
          {look.isPending ? 'Se caută…' : 'Caută o versiune nouă'}
        </Button>
      )}
      <span aria-live="polite" className="text-muted-foreground">
        {look.isError || found?.check_error
          ? 'Nu am putut căuta. Verificați conexiunea la internet.'
          : found && (found.update_available ? `Există versiunea ${shownVersion(found.latest_release)}.` : 'Aveți cea mai nouă versiune.')}
      </span>
    </div>
  )
}
