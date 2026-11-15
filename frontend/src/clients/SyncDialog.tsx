import { useQueryClient } from '@tanstack/react-query'
import { Download } from 'lucide-react'
import { useState } from 'react'
import { DateField } from '@/components/DateField'
import { PillTabs } from '@/components/PillTabs'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ANAF_KEEPS_DAYS, ANAF_KEEPS_LINE } from '../anafKeeps'
import { ApiError, api } from '../api'
import type { SyncPeriod } from '../api'
import { errorMessage } from '../errorMessages'
import { countOf, daysAgo, today } from '../format'
import type { Client, SyncResult } from '../types'
import { describeSyncResult } from './syncOutcome'

const PERIODS = [1, 2, 3, 5, 10, 15, 30].map((days) => ({
  value: days,
  label: days === 1 ? 'Ultima zi' : `Ultimele ${countOf(days, 'zi', 'zile')}`,
}))
const USUAL_PERIOD = 5

type Outcome = { result: SyncResult } | { error: unknown } | 'running' | 'waiting'

/** Downloading invoices from ANAF for one client or for all, for the last days or between two dates. */
export function SyncDialog({ clients, someAreOff, onClose }: { clients: Client[] | null; someAreOff: boolean; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [days, setDays] = useState<number | null>(USUAL_PERIOD)
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [outcomes, setOutcomes] = useState<Record<string, Outcome> | null>(null)

  if (!clients) return null
  const period: SyncPeriod | null = days ? { days, cover_gap: true } : start ? { start, end: end || today() } : null
  const running = outcomes !== null && Object.values(outcomes).some((outcome) => outcome === 'running' || outcome === 'waiting')

  const download = async () => {
    if (!period) return
    const progress: Record<string, Outcome> = Object.fromEntries(clients.map((client) => [client.cui, 'waiting']))
    const show = (cui: string, outcome: Outcome) => setOutcomes({ ...Object.assign(progress, { [cui]: outcome }) })
    // One client at a time: ANAF is asked with the same login, and the program allows one download at once.
    for (const client of clients) {
      show(client.cui, 'running')
      try {
        show(client.cui, { result: await api.sync(client.cui, period) })
      } catch (error) {
        show(client.cui, { error })
        // Without a login every other client would fail the same way.
        if (error instanceof ApiError && error.code === 'login_needed') {
          clients.forEach((other) => progress[other.cui] === 'waiting' && show(other.cui, { error }))
          break
        }
      }
    }
    queryClient.invalidateQueries({ queryKey: ['clients'] })
    queryClient.invalidateQueries({ queryKey: ['invoices'] })
    queryClient.invalidateQueries({ queryKey: ['proposed-rules'] })
    queryClient.invalidateQueries({ queryKey: ['auth'] }) // a refused login must show in the top bar
  }
  const close = () => {
    setOutcomes(null)
    onClose()
  }

  return (
    <Dialog open onOpenChange={(isOpen) => !isOpen && !running && close()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-heading text-3xl">Descarcă facturile</DialogTitle>
          <DialogDescription className="text-lg">
            {clients.length === 1
              ? `${clients[0].name} · CUI ${clients[0].cui}`
              : someAreOff
                ? `Pentru cei ${countOf(clients.length, 'un client', 'clienți')} porniți`
                : `Pentru toți cei ${countOf(clients.length, 'client', 'clienți')}`}
          </DialogDescription>
        </DialogHeader>

        {outcomes ? (
          <ul className="flex max-h-[50vh] flex-col gap-2 overflow-y-auto">
            {clients.map((client) => (
              <li key={client.cui} className="rounded-xl bg-background px-4 py-3">
                <span className="font-semibold">{client.name}</span>: {describe(outcomes[client.cui], days)}
              </li>
            ))}
          </ul>
        ) : (
          <>
            <div className="flex flex-col gap-3">
              <p className="text-xl font-bold">Din ce perioadă?</p>
              <PillTabs
                label="Perioada"
                options={PERIODS}
                value={days}
                onChange={(chosen) => {
                  setDays(chosen)
                  setStart('')
                  setEnd('')
                }}
              />
            </div>
            <div className="flex flex-col gap-3 rounded-xl bg-background px-5 py-4.5">
              <p className="font-bold">sau alegeți zilele</p>
              <div className="flex flex-wrap gap-x-5 gap-y-3.5">
                <DateField id="sync-start" label="De la" value={start} min={daysAgo(ANAF_KEEPS_DAYS)} max={end || today()} onChange={(day) => { setStart(day); setDays(null) }} />
                <DateField id="sync-end" label="Până la" value={end} min={start || daysAgo(ANAF_KEEPS_DAYS)} max={today()} onChange={(day) => { setEnd(day); setDays(null) }} />
              </div>
            </div>
            <p className="text-muted-foreground">{ANAF_KEEPS_LINE}</p>
          </>
        )}

        <DialogFooter>
          {outcomes ? (
            <Button variant="secondary" size="lg" disabled={running} onClick={close}>
              {running ? 'Se descarcă…' : 'Gata'}
            </Button>
          ) : (
            <>
              <Button variant="outline" size="lg" onClick={close}>Renunță</Button>
              <Button size="lg" disabled={!period} onClick={download}>
                <Download aria-hidden />
                Descarcă facturile
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function describe(outcome: Outcome, askedDays: number | null): string {
  if (outcome === 'waiting') return 'așteaptă'
  if (outcome === 'running') return 'se descarcă…'
  return 'error' in outcome ? errorMessage(outcome.error) : describeSyncResult(outcome.result, askedDays)
}
