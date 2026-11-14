import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Notice } from '@/components/Notice'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { api } from '../api'
import { showError } from '../errorMessages'
import { formatWhen } from '../format'
import type { BackupStatus } from '../types'

/** When the last copy was made, when the next one comes, and the button that makes one now. */
export function BackupStatusCard({ status }: { status: BackupStatus }) {
  const queryClient = useQueryClient()
  const make = useMutation({
    mutationFn: api.makeBackup,
    // Returned, so the button stays busy until the new copy is in the list below.
    onSuccess: () => {
      toast.success('Copia de siguranță a fost făcută.')
      return queryClient.invalidateQueries({ queryKey: ['backups'] })
    },
    onError: (error) => {
      showError(error)
      queryClient.invalidateQueries({ queryKey: ['backups'] }) // the failure itself is shown here
    },
  })

  if (!status.folder) {
    return (
      <Notice tone="attention" className="text-lg font-semibold">
        Alegeți mai întâi un folder. Până atunci programul nu face nicio copie.
      </Notice>
    )
  }
  return (
    <>
      {!status.folder_found && (
        <Notice tone="attention">
          {/* A path or an error may have no space to break at: it breaks anywhere instead of spilling. */}
          <p className="font-semibold [overflow-wrap:anywhere]">Folderul nu a fost găsit: {status.folder}</p>
          <p>Dacă este pe un stick USB sau pe alt disc, conectați-l. Programul încearcă din nou singur.</p>
        </Notice>
      )}
      {status.folder_found && status.last_failure && (
        <Notice tone="attention">
          <p className="font-semibold">Ultima copie nu a reușit ({formatWhen(status.last_failure.at)}).</p>
          <p className="text-[0.9rem] [overflow-wrap:anywhere]">Detalii tehnice: {status.last_failure.error}</p>
        </Notice>
      )}
      {/* Green only once there is a copy: before that there is nothing to be reassured about.
          With the folder away the program reports no copies at all, which says nothing about
          the copies in it: neither "none yet" nor the time of the next one is true then. */}
      <section
        aria-label="Starea copiilor"
        className={cn(
          'flex flex-wrap items-center gap-x-5 gap-y-3.5 rounded-2xl px-5 py-4.5',
          status.last_at ? 'bg-done text-done-foreground' : 'border bg-card',
        )}
      >
        <div className="min-w-0 flex-[1_1_380px]">
          <p className="text-lg font-bold">
            {!status.folder_found
              ? 'Copiile se văd din nou după ce folderul este la locul lui.'
              : status.last_at ? `Ultima copie: ${formatWhen(status.last_at)}` : 'Nu există încă nicio copie.'}
          </p>
          <p className="text-foreground">
            Programul face singur o copie la fiecare 24 de ore, cât timp este pornit.
            {status.folder_found && status.next_due_at &&
              ` Următoarea: ${status.due_now ? 'în cel mult un sfert de oră' : formatWhen(status.next_due_at)}.`}
          </p>
        </div>
        <Button size="lg" className="font-bold" disabled={make.isPending || !status.folder_found} onClick={() => make.mutate()}>
          {make.isPending ? 'Se face copia…' : 'Fă o copie acum'}
        </Button>
      </section>
    </>
  )
}
