import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Notice } from '@/components/Notice'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { api } from '../api'
import { errorMessage } from '../errorMessages'
import { formatFromWhen } from '../format'
import { useRestartingJob } from '../layout/useRestartingJob'
import type { Snapshot } from '../types'

// When the program refuses to start a restore over the copy, the copy is no longer where
// the list showed it. The usual sentence for this code is about making a copy.
const WHY_NOT_STARTED = { backup_error: 'Restaurarea nu a putut începe: copia nu mai este în folder.' }

/**
 * Putting a snapshot back, from the warning to the result. It replaces everything saved
 * since, so it asks for a tick first. Once started the window cannot be closed: the
 * program is stopped, and the page has nothing to talk to until it is back.
 */
export function RestoreDialog({ snapshot, onClose }: { snapshot: Snapshot; onClose: () => void }) {
  const queryClient = useQueryClient()
  const copy = `copia ${formatFromWhen(snapshot.at)}` // "copia de azi, 09:30", "copia din 09.11.2026, 14:02"
  const [understood, setUnderstood] = useState(false)
  const job = useRestartingJob({
    name: 'backups',
    start: () => api.restoreBackup(snapshot.name),
    read: api.backups,
    recordOf: (latest) => latest?.last_restore,
  })
  const mayClose = job.phase === 'asking' || job.phase === 'failed' || job.phase === 'slow'
  const close = () => {
    queryClient.invalidateQueries({ queryKey: ['backups'] })
    onClose()
  }

  return (
    <Dialog open onOpenChange={(isOpen) => !isOpen && mayClose && close()}>
      <DialogContent showCloseButton={mayClose}>
        {job.phase === 'asking' && (
          <>
            <DialogHeader>
              <DialogTitle className="font-heading text-3xl">Restaurați {copy}?</DialogTitle>
              <DialogDescription className="sr-only">Ce se întâmplă la restaurare</DialogDescription>
            </DialogHeader>
            {/* The ticks are named: put back unticked, an invoice could be imported into SAGA a second time. */}
            <Notice tone="attention" className="font-semibold">
              Tot ce ați lucrat după această copie dispare din program: facturile descărcate, conturile alese, bifele
              „importat în SAGA”, regulile, clienții adăugați, setările și cheile schimbate. Dispar și rândurile din
              jurnal de după copie.
            </Notice>
            <ul className="flex list-disc flex-col gap-2 pl-6">
              <li>Înainte de restaurare se face o copie a bazei de date de acum, ca să vă puteți întoarce.</li>
              <li>Programul se oprește câteva secunde și pornește singur din nou.</li>
              <li>Fișierele deja scrise pentru SAGA rămân pe disc așa cum sunt.</li>
            </ul>
            <div className="flex min-h-12 items-start gap-3">
              <Checkbox id="restore-understood" className="mt-1" checked={understood} onCheckedChange={(checked) => setUnderstood(checked === true)} />
              <Label htmlFor="restore-understood" className="leading-snug">Am înțeles că se pierde ce am lucrat după {copy}.</Label>
            </div>
            <div className="flex flex-wrap gap-2.5">
              <Button size="lg" className="font-bold" disabled={!understood} onClick={job.begin}>Restaurează</Button>
              <Button size="lg" variant="outline" onClick={close}>Renunță</Button>
            </div>
          </>
        )}

        {job.phase === 'working' && (
          <>
            <DialogHeader>
              <DialogTitle className="font-heading text-3xl">Se restaurează copia…</DialogTitle>
              <DialogDescription className="text-lg text-foreground">
                Nu închideți această pagină. Durează de obicei mai puțin de un minut.
              </DialogDescription>
            </DialogHeader>
            <p className="text-muted-foreground">Această fereastră se schimbă singură când programul este gata.</p>
            <div aria-hidden className="h-2.5 overflow-hidden rounded-full bg-muted">
              <div className="h-full w-2/5 animate-pulse rounded-full bg-primary" />
            </div>
          </>
        )}

        {job.phase === 'done' && (
          <>
            <DialogHeader>
              <DialogTitle className="sr-only">Copia a fost restaurată</DialogTitle>
              <DialogDescription className="sr-only">Restaurarea s-a terminat</DialogDescription>
            </DialogHeader>
            <Notice tone="done" className="font-semibold">Programul are din nou datele din {copy}.</Notice>
            {/* A fresh load: everything on screen was read from the database that was replaced.
                autoFocus: the button pressed to start is gone, so the keyboard would be nowhere. */}
            <Button autoFocus size="lg" className="justify-self-start font-bold" onClick={() => window.location.reload()}>Continuă</Button>
          </>
        )}

        {job.phase === 'failed' && (
          <>
            <DialogHeader>
              <DialogTitle className="sr-only">Restaurarea nu a reușit</DialogTitle>
              <DialogDescription className="sr-only">Baza de date a rămas cea de dinainte</DialogDescription>
            </DialogHeader>
            <Notice tone="attention" className="font-semibold">
              {job.startError
                ? errorMessage(job.startError, WHY_NOT_STARTED)
                : 'Restaurarea nu a reușit. Programul are aceleași date ca înainte.'}
            </Notice>
            <p className="text-[0.9rem] text-muted-foreground">
              Detalii tehnice: {job.startError ? job.startError.message : job.record?.error}
            </p>
            <Button autoFocus size="lg" variant="outline" className="justify-self-start" onClick={close}>Închide</Button>
          </>
        )}

        {job.phase === 'slow' && (
          <>
            <DialogHeader>
              <DialogTitle className="font-heading text-3xl">Durează mai mult decât de obicei</DialogTitle>
              <DialogDescription className="text-lg text-foreground">
                Programul nu a spus încă dacă restaurarea s-a terminat. Puteți închide această fereastră.
              </DialogDescription>
            </DialogHeader>
            <p>Dacă pagina nu mai răspunde, faceți dublu clic pe „AutoSaga” de pe Desktop și uitați-vă din nou aici.</p>
            <Button size="lg" variant="outline" className="justify-self-start" onClick={close}>Închide</Button>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
