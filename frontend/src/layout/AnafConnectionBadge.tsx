import { useQuery } from '@tanstack/react-query'
import { Check, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { cn } from '@/lib/utils'
import { api } from '../api'
import { countOf } from '../format'
import { AnafLoginDialog } from './AnafLoginDialog'

/** Whether the saved ANAF login still works and for how many days; opens the login steps. */
export function AnafConnectionBadge() {
  const [loginOpen, setLoginOpen] = useState(false)
  const { data: status } = useQuery({ queryKey: ['auth'], queryFn: api.authStatus })
  const connected = status !== undefined && status.state !== 'needs_login'

  return (
    <>
      <button
        type="button"
        onClick={() => setLoginOpen(true)}
        className={cn(
          'flex min-h-11 items-center gap-2 rounded-full px-4 font-semibold outline-none focus-visible:ring-3 focus-visible:ring-ring/50',
          connected ? 'bg-done text-done-foreground' : 'bg-attention text-attention-foreground',
        )}
      >
        {connected ? <Check aria-hidden className="size-5" /> : <TriangleAlert aria-hidden className="size-5" />}
        {connected
          ? `Conectat la ANAF · încă ${countOf(status.refresh_days_left ?? 0, 'o zi', 'zile')}`
          : 'Conectați-vă la ANAF'}
      </button>
      <AnafLoginDialog open={loginOpen} onClose={() => setLoginOpen(false)} />
    </>
  )
}
