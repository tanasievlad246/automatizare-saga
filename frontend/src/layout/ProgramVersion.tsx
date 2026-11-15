import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { api } from '../api'
import type { UpdateStatus } from '../types'
import { COULD_NOT_LOOK, shownVersion, whatTheLookFound } from './programUpdate'

/** At the foot of the menu, which ends with it: the version installed, and a way to look for a newer one now. */
export function ProgramVersion({ status, onUpdate }: { status: UpdateStatus; onUpdate: () => void }) {
  const queryClient = useQueryClient()
  const look = useMutation({
    mutationFn: () => api.updateStatus(true),
    // What it found is what the rest of the page shows, the notice on top included.
    onSuccess: (found) => queryClient.setQueryData(['program-update'], found),
  })

  return (
    <div className="mt-6 flex flex-col gap-2 px-3.5 text-[0.95rem]">
      <span className="font-medium">AutoSaga {shownVersion(status.version)}</span>
      {status.update_available ? (
        <>
          <span className="text-muted-foreground">Există versiunea {shownVersion(status.latest_release)}.</span>
          <Button className="min-h-10 self-start" onClick={onUpdate}>Actualizează programul</Button>
        </>
      ) : (
        <Button variant="outline" className="min-h-10 self-start" disabled={look.isPending} onClick={() => look.mutate()}>
          {look.isPending ? 'Se caută…' : 'Caută o versiune nouă'}
        </Button>
      )}
      {/* Said from the status the page has now, not from what this look found: read again
          later, the status may know of a newer version, and the notice on top would say so. */}
      <span aria-live="polite" className="text-muted-foreground">
        {look.isError ? COULD_NOT_LOOK : look.isSuccess && !status.update_available && whatTheLookFound(status)}
      </span>
    </div>
  )
}
