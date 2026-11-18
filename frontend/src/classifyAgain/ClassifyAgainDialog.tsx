import { useQueryClient } from '@tanstack/react-query'
import { RotateCcw } from 'lucide-react'
import { useState } from 'react'
import { WaitingSpinner } from '@/components/WaitingSpinner'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { api } from '../api'
import { errorMessage } from '../errorMessages'
import type { ClassifyAgainResult, Client } from '../types'
import { CLASSIFY_AGAIN_TITLE, JEV_TICK, KEPT, forWhom, introLine, outcomeLine, startLabel } from './classifyAgainTexts'

/** Where one client stands: not started, running, done (with whether Jev was left out for an earlier client), failed. */
type Outcome = 'waiting' | 'running' | { result: ClassifyAgainResult; jevStoppedBefore: boolean } | { error: unknown }

/**
 * The invoices to check, or waiting for Jev, of one client or of several, sent back through the
 * rules and, when ticked, Jev. One client at a time, as the download does: the program takes one
 * at once. Once Jev stops answering, the clients after get the rules alone.
 */
export function ClassifyAgainDialog({ clients, onClose }: { clients: Client[] | null; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [jev, setJev] = useState(true)
  const [outcomes, setOutcomes] = useState<Record<string, Outcome> | null>(null)

  if (!clients) return null
  const total = clients.reduce((sum, client) => sum + client.review_count + client.waiting_count, 0)
  const running = outcomes !== null && Object.values(outcomes).some((outcome) => outcome === 'running' || outcome === 'waiting')

  const start = async () => {
    const progress: Record<string, Outcome> = Object.fromEntries(clients.map((client) => [client.cui, 'waiting']))
    const show = (cui: string, outcome: Outcome) => setOutcomes({ ...Object.assign(progress, { [cui]: outcome }) })
    let askJev = jev
    for (const client of clients) {
      show(client.cui, 'running')
      try {
        const result = await api.classifyAgain(client.cui, askJev)
        show(client.cui, { result, jevStoppedBefore: jev && !askJev })
        askJev = askJev && !result.jev_stopped
      } catch (error) {
        show(client.cui, { error })
      }
    }
    for (const key of ['clients', 'invoices', 'invoice', 'proposed-rules', 'costs', 'jev-calls']) {
      queryClient.invalidateQueries({ queryKey: [key] })
    }
  }
  const close = () => {
    setOutcomes(null)
    setJev(true)
    onClose()
  }

  return (
    <Dialog open onOpenChange={(isOpen) => !isOpen && !running && close()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-heading text-3xl">{CLASSIFY_AGAIN_TITLE}</DialogTitle>
          <DialogDescription className="text-lg">{forWhom(clients)}</DialogDescription>
        </DialogHeader>

        {outcomes ? (
          <ul aria-live="polite" className="flex max-h-[50vh] flex-col gap-2 overflow-y-auto">
            {clients.map((client) => (
              <li key={client.cui} className="flex items-center gap-2 rounded-xl bg-background px-4 py-3">
                {outcomes[client.cui] === 'running' && <WaitingSpinner className="size-5" />}
                <p>
                  <span className="font-semibold">{client.name}</span>: {describe(outcomes[client.cui])}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <>
            <p>{introLine(total, jev)}</p>
            <div className="flex flex-col gap-1.5 rounded-xl bg-background px-4.5 py-3.5">
              <p className="font-bold">Rămân cum sunt</p>
              <ul className="list-disc pl-5">
                {KEPT.map((kept) => <li key={kept}>{kept}</li>)}
              </ul>
            </div>
            <div className="flex items-start gap-3">
              <Checkbox id="classify-again-jev" className="mt-1" checked={jev} onCheckedChange={(checked) => setJev(checked === true)} />
              <div className="flex flex-col gap-1">
                <Label htmlFor="classify-again-jev" className="text-base font-bold">{JEV_TICK.label}</Label>
                <p className="text-[0.9rem] text-muted-foreground">{JEV_TICK.help}</p>
              </div>
            </div>
          </>
        )}

        <DialogFooter>
          {outcomes ? (
            <Button variant="secondary" size="lg" disabled={running} onClick={close}>
              {running ? 'Se clasifică…' : 'Gata'}
            </Button>
          ) : (
            <>
              <Button variant="outline" size="lg" onClick={close}>Renunță</Button>
              {/* Allowed to wrap: "cele 25 de facturi" is longer than a phone is wide. */}
              <Button size="lg" className="h-auto min-h-12 max-w-full py-2 text-left whitespace-normal" disabled={total === 0} onClick={start}>
                <RotateCcw aria-hidden />
                {startLabel(total)}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function describe(outcome: Outcome): string {
  if (outcome === 'waiting') return 'așteaptă'
  if (outcome === 'running') return 'se clasifică…'
  return 'error' in outcome ? errorMessage(outcome.error) : outcomeLine(outcome.result, outcome.jevStoppedBefore)
}
