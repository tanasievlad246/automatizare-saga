import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { ErrorNotice } from '@/components/ErrorNotice'
import { PageTitle } from '@/components/PageTitle'
import { api } from '../api'
import { cn } from '@/lib/utils'
import type { BackupStatus, Snapshot } from '../types'
import { BackupFolderCard } from './BackupFolderCard'
import { BackupStatusCard } from './BackupStatusCard'
import { RestoreDialog } from './RestoreDialog'
import { SnapshotsList } from './SnapshotsList'
import { WipeCard } from './WipeCard'

/** Copies of the database: where they go, when the last one was made, and putting one back. */
export function BackupsPage() {
  const { data: status, error, isPending } = useQuery({ queryKey: ['backups'], queryFn: api.backups, refetchOnWindowFocus: true })
  const [restoring, setRestoring] = useState<Snapshot | null>(null)

  return (
    <div className="flex flex-col gap-5">
      <PageTitle title="Copii de siguranță">
        Programul păstrează copii ale bazei de date (clienți, facturi, conturi, reguli, setări) într-un folder ales de
        dumneavoastră.
      </PageTitle>
      {error && <ErrorNotice error={error} />}
      {isPending && <p role="status" className="text-lg text-muted-foreground">Se încarcă…</p>}
      {status && (
        // On a wide screen the list of copies stands beside the folder and the last copy; with
        // no list (no folder chosen, or it is away) the cards take the whole width.
        <div className={cn('grid items-start gap-5', listed(status) && 'min-[96rem]:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]')}>
          <div className="flex min-w-0 flex-col gap-5">
            {/* The key remounts the card when the saved folder changes, so the field shows it. */}
            <BackupFolderCard key={status.folder ?? ''} saved={status.folder ?? ''} />
            <BackupStatusCard status={status} />
          </div>
          {/* Not with the folder away (a stick taken out): the program then lists no copies,
              and an empty list would read as "there are none". */}
          {listed(status) && <SnapshotsList status={status} onRestore={setRestoring} />}
          {restoring && <RestoreDialog snapshot={restoring} onClose={() => setRestoring(null)} />}
        </div>
      )}
      {/* Last on the page, across its whole width: the one action that deletes. */}
      {status && <WipeCard status={status} />}
    </div>
  )
}

/** The copies are listed only from a folder that is chosen and can be reached. */
function listed(status: BackupStatus): boolean {
  return Boolean(status.folder && status.folder_found)
}
