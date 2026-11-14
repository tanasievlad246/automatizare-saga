import { useState } from 'react'
import { Button } from '@/components/ui/button'
import type { UpdateStatus } from '../types'
import { shownVersion } from './programUpdate'
import { UpdateDialog } from './UpdateDialog'

/** On top of every screen while a newer release exists: what it is, and the button to take it. */
export function UpdateNotice({ status }: { status: UpdateStatus }) {
  const [asking, setAsking] = useState(false)
  return (
    <section
      aria-label="Versiune nouă"
      className="mb-6 flex flex-wrap items-center gap-x-5 gap-y-3.5 rounded-2xl bg-fresh px-5 py-4.5 text-fresh-foreground"
    >
      <div className="min-w-0 flex-[1_1_380px]">
        <p className="text-lg font-bold">
          Există o versiune nouă a programului: {shownVersion(status.latest_release)}
        </p>
        <p className="mt-0.5 text-foreground">Facturile, clienții, regulile și setările dumneavoastră rămân neschimbate.</p>
      </div>
      <Button size="lg" className="font-bold" onClick={() => setAsking(true)}>Actualizează programul</Button>
      {asking && <UpdateDialog status={status} onClose={() => setAsking(false)} />}
    </section>
  )
}
