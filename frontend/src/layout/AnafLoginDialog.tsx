import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { ErrorNotice } from '@/components/ErrorNotice'
import { Notice } from '@/components/Notice'
import { ApiError, api } from '../api'
import { errorDetail, showError } from '../errorMessages'
import { nextView, openingView } from './certificateLogin'
import type { LoginEvent, LoginView } from './certificateLogin'

// ANAF answered that the Client ID or the Callback URL is not the registered one: here the
// person can correct it, which the general sentence for this code does not say.
const SETTINGS_WRONG = {
  config_error:
    'ANAF nu recunoaște Client ID-ul sau Callback URL-ul. Verificați Client ID-ul la „Chei și parole”. Pentru Callback URL, urmați pașii de la „Cum obțin Client ID și Client Secret de la ANAF?”.',
}

/**
 * The yearly ANAF login. Where the program can ask Windows for the certificate, that is the
 * first way: Windows shows its certificate window and the token its PIN window, and the
 * program receives only ANAF's answer. The other way is ANAF's own page in the browser: all
 * the program receives is the address that page ends on, which the person copies back here.
 */
export function AnafLoginDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [address, setAddress] = useState('')
  // What the person chose to look at; until then the window shows its first view. Reading
  // the login state may take longer than opening the window, so the first view is worked out
  // at each draw and not fixed at the start.
  const [chosen, setChosen] = useState<LoginView | null>(null)
  // The same, for the answers of the program: a mutation keeps the callbacks it was started
  // with, which would see the window as it was then and not as it is when the answer comes.
  const shown = useRef<LoginView | null>(null)
  const attempts = useRef(0)
  const { data: status } = useQuery({ queryKey: ['auth'], queryFn: api.authStatus })
  const view = chosen ?? openingView(status?.certificate_login)
  const show = (next: LoginView | null) => {
    shown.current = next
    setChosen(next)
  }
  const go = (event: LoginEvent) => show(nextView(shown.current ?? view, event))

  const refreshLogin = () => {
    // The keys screen shows the tokens this login brought.
    for (const key of ['auth', 'secrets']) queryClient.invalidateQueries({ queryKey: [key] })
  }
  const finish = () => {
    toast.success('Conectat la ANAF.')
    setAddress('')
    show(null)
    onClose()
  }
  const close = () => {
    show(null) // a pasted address stays: only a finished login clears it
    onClose()
  }

  const openAnaf = useMutation({
    mutationFn: api.startLogin,
    onSuccess: ({ authorize_url }) => window.open(authorize_url, '_blank', 'noopener'),
    onError: showError,
  })
  const connect = useMutation({
    mutationFn: () => api.finishLogin(address),
    onSuccess: () => {
      refreshLogin()
      finish()
    },
    onError: showError,
  })
  // The variable is the number of the try. A try the person gave up on may still end in a
  // saved login: the top bar's chip follows it, and nothing else on screen changes.
  const askWindows = useMutation({
    mutationFn: (attempt: number) => api.loginWithCertificate().then((login) => ({ login, attempt })),
    // Whichever try it was, the person did connect: the chip refreshes, the message says so
    // and the window, if it is open, closes. Only a failure of a try nobody waits for is silent.
    onSuccess: () => {
      refreshLogin()
      finish()
    },
    onError: (error, attempt) => {
      if (shown.current) go({ type: 'failed', attempt, error })
    },
  })
  const ask = () => {
    attempts.current += 1
    go({ type: 'ask', attempt: attempts.current })
    askWindows.mutate(attempts.current)
  }

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && close()}>
      <DialogContent>
        {view.kind === 'certificate' && (
          <>
            <DialogHeader>
              <DialogTitle className="font-heading text-3xl">Conectare la ANAF</DialogTitle>
              <DialogDescription className="text-lg">
                Aveți nevoie de tokenul USB și de PIN-ul lui. Se face cam o dată pe an.
              </DialogDescription>
            </DialogHeader>
            {view.note && <Notice tone="attention">{view.note}</Notice>}
            <ol className="flex list-decimal flex-col gap-2 pl-6">
              <li>Introduceți tokenul USB în calculator.</li>
              <li>Apăsați butonul de mai jos. Windows vă arată certificatele: alegeți-l pe al dumneavoastră.</li>
              <li>Scrieți PIN-ul în fereastra tokenului.</li>
            </ol>
            <Button size="lg" className="w-fit justify-self-start" onClick={ask}>
              Conectează-mă cu certificatul
            </Button>
            <BrowserLink onClick={() => go({ type: 'browser' })}>Nu merge așa? Conectare prin browser</BrowserLink>
          </>
        )}

        {view.kind === 'waiting' && (
          <>
            <DialogHeader>
              <DialogTitle className="font-heading text-3xl">Se așteaptă certificatul…</DialogTitle>
              <DialogDescription className="text-lg text-foreground">
                Alegeți certificatul în fereastra Windows, apoi scrieți PIN-ul.
              </DialogDescription>
            </DialogHeader>
            <p className="text-muted-foreground">
              Fereastra poate fi în spatele browserului. Dacă nu o vedeți, uitați-vă în bara de jos a ecranului.
            </p>
            <div aria-hidden className="h-2.5 overflow-hidden rounded-full bg-muted">
              <div className="h-full w-2/5 animate-pulse rounded-full bg-primary" />
            </div>
            <Button size="lg" variant="outline" className="w-fit justify-self-start" onClick={() => go({ type: 'giveUp' })}>
              Renunță
            </Button>
          </>
        )}

        {view.kind === 'failed' && (
          <>
            <DialogHeader>
              <DialogTitle className="font-heading text-3xl">Conectare la ANAF</DialogTitle>
              <DialogDescription className="sr-only">Conectarea cu certificatul nu a reușit.</DialogDescription>
            </DialogHeader>
            {view.error instanceof ApiError && view.error.code === 'login_refused' ? (
              <>
                <Notice tone="attention">ANAF nu a acceptat certificatul.</Notice>
                <p>Verificați că este certificatul cu care intrați în SPV și că nu a expirat.</p>
                <p className="text-[0.9rem] text-muted-foreground [overflow-wrap:anywhere]">
                  Detalii tehnice: {errorDetail(view.error)}
                </p>
              </>
            ) : (
              <ErrorNotice error={view.error} here={SETTINGS_WRONG} />
            )}
            <div className="flex flex-wrap gap-2.5">
              <Button size="lg" onClick={ask}>Încearcă din nou</Button>
              <Button size="lg" variant="outline" onClick={() => go({ type: 'browser' })}>
                Conectare prin browser
              </Button>
            </div>
          </>
        )}

        {view.kind === 'browser' && (
          <>
            <DialogHeader>
              <DialogTitle className="font-heading text-3xl">Conectare la ANAF</DialogTitle>
              <DialogDescription className="text-lg">
                Se face cam o dată pe an. Aveți nevoie de tokenul USB și de PIN.
              </DialogDescription>
            </DialogHeader>
            <ol className="flex flex-col gap-5">
              <Step number={1}>
                <p className="text-lg font-semibold">Introduceți tokenul USB în calculator.</p>
              </Step>
              <Step number={2}>
                <p className="text-lg font-semibold">
                  Apăsați butonul. Se deschide pagina ANAF: alegeți certificatul și scrieți PIN-ul.
                </p>
                <Button size="lg" className="self-start" disabled={openAnaf.isPending} onClick={() => openAnaf.mutate()}>
                  Deschide pagina ANAF
                </Button>
              </Step>
              <Step number={3}>
                <p className="text-lg font-semibold">La sfârșit apare o pagină cu eroare. Este normal.</p>
                <p>Copiați toată adresa din bara de adrese a acelei pagini și lipiți-o aici, în cel mult un minut.</p>
                <p className="rounded-lg bg-background px-3.5 py-2.5 font-mono text-[0.9rem] text-muted-foreground">
                  Adresa arată așa: https://localhost/callback?code=…
                </p>
                <Label htmlFor="anaf-address">Adresa copiată</Label>
                <Textarea
                  id="anaf-address"
                  rows={3}
                  value={address}
                  onChange={(event) => setAddress(event.target.value)}
                />
                <Button
                  className="self-start bg-done-foreground hover:bg-done-foreground/85"
                  disabled={!address.trim() || connect.isPending}
                  onClick={() => connect.mutate()}
                >
                  {connect.isPending ? 'Se conectează…' : 'Termină conectarea'}
                </Button>
              </Step>
            </ol>
            <p className="text-muted-foreground">PIN-ul se scrie doar în pagina ANAF. Programul nu îl vede.</p>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

/** A quiet way to the other login, drawn as a link. */
function BrowserLink({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      className="min-h-11 w-fit justify-self-start font-semibold text-primary underline underline-offset-2"
      onClick={onClick}
    >
      {children}
    </button>
  )
}

function Step({ number, children }: { number: number; children: ReactNode }) {
  return (
    <li className="flex gap-4">
      <div
        aria-hidden
        className="flex size-11 shrink-0 items-center justify-center rounded-full bg-secondary font-heading text-xl font-bold text-secondary-foreground"
      >
        {number}
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-3 pt-2">{children}</div>
    </li>
  )
}
