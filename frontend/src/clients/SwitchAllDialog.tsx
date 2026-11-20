import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { api } from '../api'
import { showError } from '../errorMessages'
import type { Client } from '../types'
import { switchAllQuestion, switchedAllToast } from './switchedOff'

/**
 * Asks before every client is switched on (`turnOn`) or off, then does it: one press changes
 * them all and cannot be taken back in one step. `someHidden`: a search shows only a part of
 * the list, so the window says the rest change too. `onDone`: the clients as they are now.
 */
export function SwitchAllDialog({
  turnOn, on, off, someHidden, onClose, onDone,
}: {
  turnOn: boolean
  on: number
  off: number
  someHidden: boolean
  onClose: () => void
  onDone: (clients: Client[]) => void
}) {
  const queryClient = useQueryClient()
  const question = switchAllQuestion(turnOn, on, off, someHidden)
  const switchAll = useMutation({
    mutationFn: () => api.setAllClientsEnabled(turnOn),
    onSuccess: (reply) => {
      // Shown at once, as the program answered them, and read again: a reading of the list
      // started before the switch is dropped, so it cannot put the earlier list back. The
      // schedule counts the clients that are on.
      queryClient.setQueryData(['clients'], reply)
      for (const key of ['clients', 'schedule']) queryClient.invalidateQueries({ queryKey: [key] })
      onDone(reply.clients)
      toast.success(switchedAllToast(turnOn, reply.clients.length))
      onClose()
    },
    onError: showError,
  })

  return (
    <Dialog open onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-heading text-3xl">{question.title}</DialogTitle>
          <DialogDescription className="text-base text-foreground">{question.lines[0]}</DialogDescription>
        </DialogHeader>
        {question.lines.slice(1).map((line) => <p key={line}>{line}</p>)}
        {question.note && <p className="text-muted-foreground">{question.note}</p>}
        <DialogFooter>
          <Button type="button" variant="outline" size="lg" onClick={onClose}>Renunță</Button>
          <Button type="button" size="lg" disabled={switchAll.isPending} onClick={() => switchAll.mutate()}>
            {question.confirm}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
