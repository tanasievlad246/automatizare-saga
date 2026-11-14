import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { api } from '../api'
import { showError } from '../errorMessages'

/**
 * The yearly ANAF login. The certificate and PIN are handled by ANAF's own page; all this
 * program receives is the address that page ends on, which the person copies back here.
 */
export function AnafLoginDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [address, setAddress] = useState('')

  const openAnaf = useMutation({
    mutationFn: api.startLogin,
    onSuccess: ({ authorize_url }) => window.open(authorize_url, '_blank', 'noopener'),
    onError: showError,
  })
  const connect = useMutation({
    mutationFn: () => api.finishLogin(address),
    onSuccess: () => {
      // The keys screen shows the tokens this login brought.
      for (const key of ['auth', 'secrets']) queryClient.invalidateQueries({ queryKey: [key] })
      toast.success('Conectat la ANAF.')
      setAddress('')
      onClose()
    },
    onError: showError,
  })

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent>
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
      </DialogContent>
    </Dialog>
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
