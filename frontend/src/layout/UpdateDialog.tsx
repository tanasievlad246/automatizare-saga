import { useQueryClient } from '@tanstack/react-query'
import { Notice } from '@/components/Notice'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { api } from '../api'
import { errorMessage } from '../errorMessages'
import type { UpdateStatus } from '../types'
import { shownVersion } from './programUpdate'
import { useRestartingJob } from './useRestartingJob'

/**
 * Updating the program, from the question to the result. Once it has started the window
 * cannot be closed: the program is stopped, and the page has nothing to talk to until it is back.
 */
export function UpdateDialog({ status, onClose }: { status: UpdateStatus; onClose: () => void }) {
  const queryClient = useQueryClient()
  const newVersion = shownVersion(status.latest_release)
  const job = useRestartingJob({
    name: 'program-update',
    start: api.startUpdate,
    read: () => api.updateStatus(),
    recordOf: (latest) => latest?.last_update,
  })
  // Closing is offered while nothing has started, after a failure, and when waiting has
  // gone on too long. After a success the only way on is "Continuă", which loads the new page.
  const mayClose = job.phase === 'asking' || job.phase === 'failed' || job.phase === 'slow'
  const close = () => {
    // Read again next time, so a second try starts from how this one ended, not from before it.
    queryClient.invalidateQueries({ queryKey: ['program-update'] })
    onClose()
  }

  return (
    <Dialog open onOpenChange={(isOpen) => !isOpen && mayClose && close()}>
      <DialogContent showCloseButton={mayClose}>
        {job.phase === 'asking' && (
          <>
            <DialogHeader>
              <DialogTitle className="font-heading text-3xl">Actualizați programul la versiunea {newVersion}?</DialogTitle>
              <DialogDescription className="sr-only">Ce se întâmplă în timpul actualizării</DialogDescription>
            </DialogHeader>
            <ul className="flex list-disc flex-col gap-2 pl-6">
              <li>Programul se oprește cam un minut și pornește singur din nou.</li>
              <li>Facturile, clienții, regulile și setările rămân neschimbate.</li>
              <li>
                Înainte de actualizare programul își păstrează o copie a bazei de date, separat de cele de pe pagina
                „Copii de siguranță”.
              </li>
            </ul>
            <div className="flex flex-wrap gap-2.5">
              <Button size="lg" className="font-bold" onClick={job.begin}>Actualizează acum</Button>
              <Button size="lg" variant="outline" onClick={close}>Nu acum</Button>
            </div>
          </>
        )}

        {job.phase === 'working' && (
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

        {job.phase === 'done' && (
          <>
            <DialogHeader>
              <DialogTitle className="sr-only">Programul a fost actualizat</DialogTitle>
              <DialogDescription className="sr-only">Actualizarea s-a terminat</DialogDescription>
            </DialogHeader>
            <Notice tone="done" className="font-semibold">Programul a fost actualizat la versiunea {newVersion}.</Notice>
            {/* A fresh load, so the page itself is the new release's too.
                autoFocus: the button pressed to start is gone, so the keyboard would be nowhere. */}
            <Button autoFocus size="lg" className="justify-self-start font-bold" onClick={() => window.location.reload()}>Continuă</Button>
          </>
        )}

        {job.phase === 'failed' && (
          <>
            <DialogHeader>
              <DialogTitle className="sr-only">Actualizarea nu a reușit</DialogTitle>
              <DialogDescription className="sr-only">Programul a rămas la versiunea pe care o avea</DialogDescription>
            </DialogHeader>
            <Notice tone="attention" className="font-semibold">
              {job.startError
                ? errorMessage(job.startError)
                : `Actualizarea nu a reușit. Programul a rămas la versiunea ${shownVersion(status.version)}, cu toate datele.`}
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
              {/* This comes up after three minutes, and an update can take far longer: the
                  window keeps asking and turns into the result by itself, so it says to wait. */}
              <DialogDescription className="text-lg text-foreground">
                Actualizarea poate dura și un sfert de oră când internetul este lent. Lăsați pagina deschisă: fereastra
                se schimbă singură.
              </DialogDescription>
            </DialogHeader>
            <p>Dacă după 20 de minute nu s-a schimbat nimic, faceți dublu clic pe „AutoSaga” de pe Desktop.</p>
            {/* A way out is kept, but a quiet one: closing does not stop the update, only the waiting for it. */}
            <p className="text-muted-foreground">Actualizarea merge mai departe și dacă închideți fereastra.</p>
            <Button variant="link" className="justify-self-start px-0" onClick={close}>Închide fereastra</Button>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
