import { useState } from 'react'
import { Button } from '@/components/ui/button'
import type { BackupStatus } from '../types'
import { WipeDialog } from './WipeDialog'
import { wipeBlockedBecause } from './wipeTexts'

/**
 * At the bottom of the page: deleting everything, to start again from zero. The button opens
 * the window that says what goes and what stays; it cannot be pressed without the backup
 * folder, where the copy made before the wipe goes.
 */
export function WipeCard({ status }: { status: BackupStatus }) {
  const [asking, setAsking] = useState(false)
  const blocked = wipeBlockedBecause(status)
  return (
    <section aria-label="Ștergerea tuturor datelor" className="flex flex-wrap items-center gap-x-6 gap-y-3.5 rounded-2xl border bg-card px-5 py-4.5">
      <div className="flex min-w-0 flex-[1_1_380px] flex-col gap-1.5">
        <h2 className="font-sans text-xl font-bold">Ștergerea tuturor datelor</h2>
        <p className="text-muted-foreground">
          Pentru un început de la zero: se șterg clienții, facturile, conturile și regulile. Înainte se face o copie de
          siguranță, pe care o puteți restaura oricând din lista copiilor. Setările și cheile rămân.
        </p>
        {blocked && <p className="font-semibold">{blocked}</p>}
      </div>
      <Button
        size="lg"
        variant="outline"
        className="border-2 border-destructive font-bold text-destructive hover:bg-destructive/10 hover:text-destructive"
        disabled={blocked !== null}
        onClick={() => setAsking(true)}
      >
        Șterge toate datele…
      </Button>
      {asking && <WipeDialog onClose={() => setAsking(false)} />}
    </section>
  )
}
