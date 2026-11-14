import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { cn } from '@/lib/utils'
import { api } from '../api'
import { describeAnafConnection } from './anafConnection'
import type { AnafConnection } from './anafConnection'
import { AnafLoginDialog } from './AnafLoginDialog'

// How each state looks: the chip's ground and the dot before the words.
const LOOKS: Record<AnafConnection['state'], { chip: string; dot: string }> = {
  checking: { chip: 'bg-muted text-foreground', dot: 'bg-muted-foreground' },
  unreachable: { chip: 'bg-muted text-foreground', dot: 'bg-destructive' },
  connected: { chip: 'bg-done text-done-foreground', dot: 'bg-done-foreground' },
  expiring: { chip: 'bg-attention text-attention-foreground', dot: 'bg-attention-foreground' },
  disconnected: { chip: 'bg-attention text-attention-foreground', dot: 'bg-destructive' },
}

/** In the top bar: whether the saved ANAF login still works and for how long; opens the login steps. */
export function AnafConnectionBadge() {
  const [loginOpen, setLoginOpen] = useState(false)
  // Looked at again when the window is returned to: a page left open overnight must not
  // keep saying "connected".
  const { data, isError } = useQuery({ queryKey: ['auth'], queryFn: api.authStatus, refetchOnWindowFocus: true })
  const connection = describeAnafConnection(data, isError)
  const canLogIn = connection.state !== 'checking' && connection.state !== 'unreachable'

  return (
    <>
      <button
        type="button"
        title={connection.hint || undefined}
        disabled={!canLogIn}
        onClick={() => setLoginOpen(true)}
        className={cn(
          // Never squeezed: in a top bar kept on one row it is the SAGA folder that gives way.
          'flex min-h-11 items-center gap-2.5 rounded-full px-4 font-semibold outline-none focus-visible:ring-3 focus-visible:ring-ring min-[60rem]:shrink-0',
          canLogIn && 'cursor-pointer',
          LOOKS[connection.state].chip,
        )}
      >
        <span aria-hidden className={cn('size-2.5 shrink-0 rounded-full', LOOKS[connection.state].dot)} />
        <span role="status">{connection.label}</span>
      </button>
      <AnafLoginDialog open={loginOpen} onClose={() => setLoginOpen(false)} />
    </>
  )
}
