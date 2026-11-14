import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api } from '../api'
import { showError } from '../errorMessages'

/** Adding one client by hand: a name and a CUI. */
export function AddClientDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [cui, setCui] = useState('')

  const save = useMutation({
    mutationFn: () => api.saveClient(cui, name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients'] })
      setName('')
      setCui('')
      onClose()
    },
    onError: showError,
  })

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-heading text-3xl">Adaugă un client</DialogTitle>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            save.mutate()
          }}
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="client-name">Numele firmei</Label>
            <Input id="client-name" value={name} onChange={(event) => setName(event.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="client-cui">CUI</Label>
            <Input id="client-cui" inputMode="numeric" value={cui} onChange={(event) => setCui(event.target.value)} />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Renunță</Button>
            <Button type="submit" disabled={!name.trim() || !cui.trim() || save.isPending}>Adaugă clientul</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
