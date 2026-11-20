import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Notice } from '@/components/Notice'
import { WaitingSpinner } from '@/components/WaitingSpinner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api } from '../api'
import { errorDetail } from '../errorMessages'
import { formatFromWhen } from '../format'
import { CONFIRM_WORD, confirmsWipe, wipeFailure } from './wipeTexts'

/**
 * Deleting every client, invoice, account and rule, from the warning to the result. It asks
 * for a word to be typed: the button stays grey until it is. While the program works the
 * window cannot be closed, so the person sees how it ended.
 */
export function WipeDialog({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const [typed, setTyped] = useState('')
  const wipe = useMutation({
    mutationFn: api.wipeData,
    // Whatever happened, what the page holds may be out of date: everything is asked again.
    onSettled: () => queryClient.invalidateQueries(),
  })
  const confirmed = confirmsWipe(typed)
  const phase = wipe.isIdle ? 'asking' : wipe.isPending ? 'working' : wipe.isSuccess ? 'done' : 'failed'
  const mayClose = phase === 'asking' || phase === 'failed'

  return (
    <Dialog open onOpenChange={(isOpen) => !isOpen && mayClose && onClose()}>
      <DialogContent showCloseButton={mayClose} className="max-h-[calc(100dvh-2rem)] overflow-y-auto">
        {phase === 'asking' && (
          <form
            className="grid gap-4"
            onSubmit={(event) => {
              event.preventDefault()
              if (confirmed) wipe.mutate()
            }}
          >
            <DialogHeader>
              <DialogTitle className="font-heading text-3xl">Ștergeți toate datele din program?</DialogTitle>
              <DialogDescription className="sr-only">Ce se șterge, ce rămâne și cum confirmați</DialogDescription>
            </DialogHeader>
            <Notice tone="attention">
              <p className="font-bold">Se șterg:</p>
              <p>
                clienții; facturile descărcate, cu conturile alese, bifele „importat în SAGA” și istoricul fiecărui cont;
                lista importurilor în SAGA; conturile și regulile; descărcările făcute și costurile Jev.
              </p>
            </Notice>
            <div className="grid gap-1.5">
              <p className="font-bold">Rămân:</p>
              <ul className="flex list-disc flex-col gap-1 pl-6">
                <li>setările: folderul SAGA, folderul copiilor, cheile din „Chei și parole”, descărcarea automată, întrebările pentru Jev;</li>
                <li>conectarea la ANAF și jurnalul;</li>
                <li>toate copiile de siguranță;</li>
                <li>fișierele de pe disc. Cele scrise deja pentru SAGA rămân în folderul SAGA: uitați-vă prin el și ștergeți ce nu trebuie importat.</li>
              </ul>
            </div>
            <p>
              Conturile și regulile de exemplu revin, ca la prima pornire. Înainte de ștergere se face o copie a bazei de date
              de acum și se verifică. Dacă nu reușește, nu se șterge nimic.
            </p>
            <div className="grid gap-1.5">
              <Label htmlFor="wipe-word" className="block text-base leading-snug font-semibold">
                Ca să confirmați, scrieți <span className="font-heading tracking-wider">{CONFIRM_WORD}</span> mai jos.
              </Label>
              <Input
                id="wipe-word"
                autoFocus
                autoComplete="off"
                autoCapitalize="characters"
                spellCheck={false}
                className="max-w-64 text-xl tracking-wider"
                value={typed}
                onChange={(event) => setTyped(event.target.value)}
              />
            </div>
            <div className="flex flex-wrap gap-2.5">
              <Button type="submit" size="lg" className="bg-destructive font-bold text-white hover:bg-destructive/90" disabled={!confirmed}>
                Fă copia și șterge datele
              </Button>
              <Button type="button" size="lg" variant="outline" onClick={onClose}>Renunță</Button>
            </div>
          </form>
        )}

        {phase === 'working' && (
          <>
            <DialogHeader>
              <DialogTitle className="font-heading text-3xl">Se face copia, apoi se șterg datele…</DialogTitle>
              <DialogDescription className="text-lg text-foreground">
                Nu închideți această pagină. Durează de obicei mai puțin de un minut.
              </DialogDescription>
            </DialogHeader>
            <div className="flex items-center gap-4">
              <WaitingSpinner />
              <p className="text-muted-foreground">Această fereastră se schimbă singură când este gata.</p>
            </div>
          </>
        )}

        {phase === 'done' && wipe.data && (
          <>
            <DialogHeader>
              <DialogTitle className="sr-only">Datele au fost șterse</DialogTitle>
              <DialogDescription className="sr-only">Ștergerea s-a terminat</DialogDescription>
            </DialogHeader>
            <Notice tone="done" className="font-semibold">Datele au fost șterse. Programul este gol, ca la prima pornire.</Notice>
            <p>
              Copia {formatFromWhen(wipe.data.kept_at)}, „făcută înainte de ștergerea datelor”, este în lista copiilor. Dacă vreți
              datele înapoi, apăsați „Restaurează” lângă ea.
            </p>
            {/* A fresh load: every screen read the data that is gone. autoFocus: the button
                pressed to start is gone, so the keyboard would be nowhere. */}
            <Button autoFocus size="lg" className="justify-self-start font-bold" onClick={() => window.location.reload()}>Continuă</Button>
          </>
        )}

        {phase === 'failed' && (
          <>
            <DialogHeader>
              <DialogTitle className="sr-only">Datele nu au fost șterse</DialogTitle>
              <DialogDescription className="sr-only">De ce nu s-a șters nimic</DialogDescription>
            </DialogHeader>
            <Notice tone="attention" className="font-semibold">{wipeFailure(wipe.error)}</Notice>
            <p className="text-[0.9rem] text-muted-foreground [overflow-wrap:anywhere]">Detalii tehnice: {errorDetail(wipe.error)}</p>
            <Button autoFocus size="lg" variant="outline" className="justify-self-start" onClick={onClose}>Închide</Button>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
