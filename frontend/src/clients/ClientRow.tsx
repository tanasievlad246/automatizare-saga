import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Trash2 } from 'lucide-react'
import { Link } from 'react-router'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { api } from '../api'
import { showError } from '../errorMessages'
import { countOf, formatWhen } from '../format'
import type { Client } from '../types'

/**
 * One client on the first screen: the switch, what is new, and the two things to do about it.
 * `blocked` keeps the download button off while the program is downloading by itself.
 */
export function ClientRow({ client, blocked, onSync }: { client: Client; blocked: boolean; onSync: () => void }) {
  const queryClient = useQueryClient()
  const off = !client.enabled
  const switchClient = useMutation({
    mutationFn: (enabled: boolean) => api.setClientEnabled(client.cui, enabled),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ['clients'] }),
        queryClient.invalidateQueries({ queryKey: ['schedule'] }),
      ]),
    onError: showError,
  })
  const remove = useMutation({
    mutationFn: () => api.removeClient(client.cui),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['clients'] }),
    onError: showError,
  })
  const confirmRemoval = () => {
    if (window.confirm(`Scoateți clientul „${client.name}” din listă? Facturile lui rămân salvate.`)) remove.mutate()
  }

  return (
    // Name, details and what is new on the left; the buttons on the right. When the buttons
    // do not fit beside them they drop to a row of their own, still at the right, so every
    // card lines up the same way.
    <div
      className={`flex flex-wrap items-center gap-x-6 gap-y-3.5 rounded-2xl border px-5.5 py-4.5 ${off ? 'border-dashed bg-muted' : 'bg-card'}`}
    >
      <div className="flex min-w-0 flex-[1_1_320px] flex-col gap-1.5">
        <div className={`text-xl font-bold ${off ? 'text-muted-foreground' : ''}`}>{client.name}</div>
        <div className="text-muted-foreground">
          CUI {client.cui} · Ultima descărcare: {formatWhen(client.last_sync_at)}
        </div>
        {off ? (
          <p className="font-semibold text-muted-foreground">Oprit: facturile lui nu se descarcă până îl porniți.</p>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            {client.new_count > 0 && (
              <Badge className="bg-fresh text-fresh-foreground">
                {countOf(client.new_count, 'o factură nouă', 'facturi noi')}
              </Badge>
            )}
            {client.review_count > 0 && (
              <Badge className="bg-attention text-attention-foreground">{client.review_count} de verificat</Badge>
            )}
            {client.new_count === 0 && client.review_count === 0 && (
              <span className="text-muted-foreground">Nimic nou</span>
            )}
          </div>
        )}
      </div>
      <div className="ml-auto flex flex-wrap items-center gap-2.5">
        <div className="flex items-center gap-2.5">
          <Switch
            checked={client.enabled}
            disabled={switchClient.isPending}
            aria-label={`${client.name}: facturile ${client.enabled ? 'se descarcă' : 'nu se descarcă'}`}
            onCheckedChange={(enabled) => switchClient.mutate(enabled)}
          />
          <span className={`w-14 font-semibold ${off ? 'text-muted-foreground' : 'text-done-foreground'}`}>
            {client.enabled ? 'Pornit' : 'Oprit'}
          </span>
        </div>
        <Button
          variant="outline"
          className="border-2 border-primary text-primary"
          aria-label={`Descarcă facturile pentru ${client.name}`}
          disabled={off || blocked}
          onClick={onSync}
        >
          Descarcă facturile
        </Button>
        <Button asChild variant="link">
          <Link to={`/clienti/${client.cui}`} aria-label={`Vezi facturile clientului ${client.name}`}>Vezi facturile</Link>
        </Button>
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Scoate clientul ${client.name} din listă`}
          disabled={remove.isPending}
          onClick={confirmRemoval}
        >
          <Trash2 aria-hidden className="text-muted-foreground" />
        </Button>
      </div>
    </div>
  )
}
