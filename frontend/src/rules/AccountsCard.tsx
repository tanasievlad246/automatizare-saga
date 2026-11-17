import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { api } from '../api'
import type { InvoiceKind } from '../types'
import { showError } from '../errorMessages'

type Account = { cont: string; description: string }

/**
 * The accounts Jev may choose from, for one kind of invoice. The description is what Jev
 * reads, so it matters. The same accounts are the ones a person picks from on an invoice.
 */
export function AccountsCard({ accounts, kind = 'received' }: { accounts: Record<string, string>; kind?: InvoiceKind }) {
  const [editing, setEditing] = useState<Account | 'new' | null>(null)
  return (
    <section className="flex flex-col gap-3.5">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
        <div className="min-w-0 flex-[1_1_320px]">
          <h2 className="text-2xl">{kind === 'issued' ? 'Conturile pentru facturi emise' : 'Conturile din care alege Jev'}</h2>
          <p className="mt-1 text-muted-foreground">
            {kind === 'issued'
              ? 'Din acestea alege Jev pentru facturile emise de clienți, și tot acestea apar la „Alege contul” pe o factură emisă.'
              : 'Când nicio regulă nu se potrivește, Jev alege unul dintre aceste conturi, după descriere.'}
          </p>
        </div>
        <Button variant="outline" onClick={() => setEditing('new')}>Adaugă un cont</Button>
      </div>
      <div className="rounded-2xl border bg-card">
        {Object.entries(accounts).map(([cont, description]) => (
          <div key={cont} className="flex flex-wrap items-center gap-x-5 gap-y-2.5 border-b px-5 py-3.5 last:border-b-0">
            <div className="min-w-20 shrink-0 font-heading text-2xl font-bold">{cont}</div>
            <div className="min-w-0 flex-[1_1_320px]">{description}</div>
            <Button variant="outline" size="sm" aria-label={`Modifică contul ${cont}`} onClick={() => setEditing({ cont, description })}>
              Modifică
            </Button>
          </div>
        ))}
        {Object.keys(accounts).length === 0 && (
          <p className="px-5 py-5 text-muted-foreground">
            Niciun cont. Fără conturi, Jev nu are din ce alege și facturile vin la dumneavoastră.
          </p>
        )}
      </div>
      {editing && <AccountDialog account={editing} kind={kind} onClose={() => setEditing(null)} />}
    </section>
  )
}

function AccountDialog({ account, kind, onClose }: { account: Account | 'new'; kind: InvoiceKind; onClose: () => void }) {
  const queryClient = useQueryClient()
  const existing = account === 'new' ? null : account
  const [cont, setCont] = useState(existing?.cont ?? '')
  const [description, setDescription] = useState(existing?.description ?? '')
  const afterChange = {
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rules'] })
      onClose()
    },
    onError: showError,
  }
  const save = useMutation({ mutationFn: () => api.saveAccount(cont.trim(), description, kind), ...afterChange })
  const remove = useMutation({ mutationFn: () => api.deleteAccount(cont, kind), ...afterChange })

  return (
    <Dialog open onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="font-heading text-3xl">{existing ? `Contul ${existing.cont}` : 'Adaugă un cont'}</DialogTitle>
          <DialogDescription className="text-lg">
            Scrieți ce se înregistrează pe acest cont. Jev alege după această descriere.
          </DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            save.mutate()
          }}
        >
          {!existing && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="account-cont">Contul</Label>
              <Input
                id="account-cont"
                placeholder={kind === 'issued' ? 'de exemplu 704 sau 707' : 'de exemplu 302 sau 371.01'}
                value={cont}
                onChange={(event) => setCont(event.target.value)}
              />
            </div>
          )}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="account-description">Ce se înregistrează pe el</Label>
            <Textarea id="account-description" rows={3} value={description} onChange={(event) => setDescription(event.target.value)} />
          </div>
          <DialogFooter className="sm:justify-between">
            {existing ? (
              <Button type="button" variant="destructive" disabled={remove.isPending} onClick={() => remove.mutate()}>
                Șterge contul
              </Button>
            ) : <span />}
            <div className="flex flex-wrap gap-2.5">
              <Button type="button" variant="outline" onClick={onClose}>Renunță</Button>
              <Button type="submit" disabled={!cont.trim() || save.isPending}>Salvează contul</Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
