import { useMutation } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { api } from '../api'
import { showError } from '../errorMessages'
import { formatFromWhen, formatSize, formatWhen } from '../format'
import type { BackupStatus, Snapshot } from '../types'

const WHO_MADE_IT: Record<Snapshot['kind'], string> = {
  auto: 'făcută de program',
  manual: 'făcută de dumneavoastră',
  'before-restore': 'făcută înaintea unei restaurări',
  'before-wipe': 'făcută înainte de ștergerea datelor',
}

/**
 * The copies that are kept, newest first, each with the button that puts it back.
 * Shown only while the folder is there: without it the program has no copies to list.
 */
export function SnapshotsList({ status, onRestore }: { status: BackupStatus; onRestore: (snapshot: Snapshot) => void }) {
  const open = useMutation({ mutationFn: api.openBackupFolder, onError: showError })
  return (
    <section aria-label="Copiile păstrate" className="overflow-hidden rounded-2xl border bg-card">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4.5 py-4">
        <h2 className="min-w-0 flex-[1_1_260px] font-sans text-xl font-bold">
          Copiile păstrate{' '}
          <span className="font-medium text-muted-foreground">· {status.count} din cel mult {status.max}</span>
        </h2>
        <Button variant="link" disabled={open.isPending} onClick={() => open.mutate()}>Deschide folderul</Button>
      </div>
      {status.snapshots.length === 0 && (
        <p className="border-t px-4.5 py-5 text-muted-foreground">Nicio copie încă. Prima apare aici după ce apăsați „Fă o copie acum”.</p>
      )}
      {status.snapshots.map((snapshot) => (
        // A grid, so that each cell wraps its own words and the button stays on the row. On a
        // phone the three facts stand one under the other, with the button beside them.
        <div key={snapshot.name} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-0.5 border-t px-4.5 py-3 sm:grid-cols-[minmax(9rem,1fr)_minmax(0,15rem)_5rem_auto]">
          <span className="font-semibold first-letter:uppercase">{formatWhen(snapshot.at)}</span>
          <span className="col-start-1 text-muted-foreground sm:col-start-auto">{WHO_MADE_IT[snapshot.kind]}</span>
          <span className="col-start-1 text-muted-foreground sm:col-start-auto sm:text-right">{formatSize(snapshot.size)}</span>
          <Button variant="outline" size="sm" className="col-start-2 row-span-3 row-start-1 sm:col-start-auto sm:row-span-1 sm:row-start-auto" aria-label={`Restaurează copia ${formatFromWhen(snapshot.at)}, ${WHO_MADE_IT[snapshot.kind]}`} onClick={() => onRestore(snapshot)}>
            Restaurează
          </Button>
        </div>
      ))}
      {status.count > 0 && (
        <p className="border-t px-4.5 py-3.5 text-[0.95rem] text-muted-foreground">
          Când se face o copie nouă și sunt deja {status.max}, cea mai veche se șterge singură.
        </p>
      )}
    </section>
  )
}
