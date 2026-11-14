import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Notice } from '@/components/Notice'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { api } from '../api'
import { errorMessage } from '../errorMessages'
import type { UpdateStatus } from '../types'
import { shownVersion, updateOutcome } from './programUpdate'

const ASK_AGAIN_EVERY = 2000 // milliseconds between looks, while the program is away

/**
 * Updating the program, from the question to the result. Once it has started the window
 * cannot be closed: the program is stopped, and the page has nothing to talk to until it is back.
 */
export function UpdateDialog({ status, onClose }: { status: UpdateStatus; onClose: () => void }) {
  const newVersion = shownVersion(status.latest_release)
  // The record of an earlier update, so that it is not taken for the end of this one.
  const [recordBefore] = useState(status.last_update?.at ?? null)
  const start = useMutation({ mutationFn: api.startUpdate })
  const latest = useQuery({
    queryKey: ['program-update', 'while-updating'],
    queryFn: () => api.updateStatus(),
    enabled: start.isSuccess,
    refetchInterval: ASK_AGAIN_EVERY,
    retry: false, // it fails on purpose while the program is stopped
    gcTime: 0,
  }).data
  const outcome = start.isSuccess ? updateOutcome(recordBefore, latest) : 'working'
  const started = start.isPending || start.isSuccess
  const stillWorking = started && outcome === 'working'
  // Closing is offered while nothing has started and after a failure. After a success the
  // only way on is "Continuă", which loads the new release's page.
  const mayClose = (!started && !start.isSuccess) || outcome === 'failed'

  return (
    <Dialog open onOpenChange={(isOpen) => !isOpen && mayClose && onClose()}>
      <DialogContent showCloseButton={mayClose}>
        {!started && !start.isError && (
          <>
            <DialogHeader>
              <DialogTitle className="font-heading text-3xl">Actualizați programul la versiunea {newVersion}?</DialogTitle>
              <DialogDescription className="sr-only">Ce se întâmplă în timpul actualizării</DialogDescription>
            </DialogHeader>
            <ul className="flex list-disc flex-col gap-2 pl-6">
              <li>Programul se oprește cam un minut și pornește singur din nou.</li>
              <li>Facturile, clienții, regulile și setările rămân neschimbate.</li>
              <li>Înainte de actualizare se face o copie a bazei de date.</li>
            </ul>
            <div className="flex flex-wrap gap-2.5">
              <Button size="lg" className="font-bold" onClick={() => start.mutate()}>Actualizează acum</Button>
              <Button size="lg" variant="outline" onClick={onClose}>Nu acum</Button>
            </div>
          </>
        )}

        {stillWorking && (
          <>
            <DialogHeader>
              <DialogTitle className="font-heading text-3xl">Programul se actualizează…</DialogTitle>
              <DialogDescription className="text-lg text-foreground">
                Nu închideți această pagină. Durează de obicei un minut.
              </DialogDescription>
            </DialogHeader>
            <p className="text-muted-foreground">Această fereastră se schimbă singură când programul este gata.</p>
            <div aria-hidden className="h-2.5 overflow-hidden rounded-full bg-muted">
              <div className="h-full w-2/5 animate-pulse rounded-full bg-primary" />
            </div>
          </>
        )}

        {outcome === 'done' && (
          <>
            <DialogHeader>
              <DialogTitle className="sr-only">Programul a fost actualizat</DialogTitle>
              <DialogDescription className="sr-only">Actualizarea s-a terminat</DialogDescription>
            </DialogHeader>
            <Notice tone="done" className="font-semibold">Programul a fost actualizat la versiunea {newVersion}.</Notice>
            {/* A fresh load, so the page itself is the new release's too. */}
            <Button size="lg" className="justify-self-start font-bold" onClick={() => window.location.reload()}>Continuă</Button>
          </>
        )}

        {(outcome === 'failed' || start.isError) && (
          <>
            <DialogHeader>
              <DialogTitle className="sr-only">Actualizarea nu a reușit</DialogTitle>
              <DialogDescription className="sr-only">Programul a rămas la versiunea pe care o avea</DialogDescription>
            </DialogHeader>
            <Notice tone="attention" className="font-semibold">
              {start.isError
                ? errorMessage(start.error)
                : `Actualizarea nu a reușit. Programul a rămas la versiunea ${shownVersion(status.version)}, cu toate datele.`}
            </Notice>
            <p className="text-[0.9rem] text-muted-foreground">
              Detalii tehnice: {start.isError ? start.error.message : latest?.last_update?.error}
            </p>
            <Button size="lg" variant="outline" className="justify-self-start" onClick={onClose}>Închide</Button>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
