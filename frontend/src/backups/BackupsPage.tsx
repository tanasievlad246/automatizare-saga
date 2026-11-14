import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { ErrorNotice } from '@/components/ErrorNotice'
import { PageTitle } from '@/components/PageTitle'
import { api } from '../api'
import type { Snapshot } from '../types'
import { BackupFolderCard } from './BackupFolderCard'
import { BackupStatusCard } from './BackupStatusCard'
import { RestoreDialog } from './RestoreDialog'
import { SnapshotsList } from './SnapshotsList'

/** Copies of the database: where they go, when the last one was made, and putting one back. */
export function BackupsPage() {
  const { data: status, error, isPending } = useQuery({ queryKey: ['backups'], queryFn: api.backups, refetchOnWindowFocus: true })
  const [restoring, setRestoring] = useState<Snapshot | null>(null)

  return (
    <div className="flex max-w-[66rem] flex-col gap-5">
      <PageTitle title="Copii de siguranță">
        Programul păstrează copii ale bazei de date (clienți, facturi, conturi, reguli, setări) într-un folder ales de
        dumneavoastră.
      </PageTitle>
      {error && <ErrorNotice error={error} />}
      {isPending && <p role="status" className="text-lg text-muted-foreground">Se încarcă…</p>}
      {status && (
        <>
          {/* The key remounts the card when the saved folder changes, so the field shows it. */}
          <BackupFolderCard key={status.folder ?? ''} saved={status.folder ?? ''} />
          <BackupStatusCard status={status} />
          {/* Not with the folder away (a stick taken out): the program then lists no copies,
              and an empty list would read as "there are none". */}
          {status.folder && status.folder_found && <SnapshotsList status={status} onRestore={setRestoring} />}
          {restoring && <RestoreDialog snapshot={restoring} onClose={() => setRestoring(null)} />}
        </>
      )}
    </div>
  )
}
