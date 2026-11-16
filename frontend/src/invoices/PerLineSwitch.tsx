import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Switch } from '@/components/ui/switch'
import { api } from '../api'
import { showError } from '../errorMessages'
import type { Client } from '../types'

/** The client's choice: an account for each line of its invoices, or one for the whole invoice. */
export function PerLineSwitch({ client }: { client: Client }) {
  const queryClient = useQueryClient()
  const turn = useMutation({
    mutationFn: (enabled: boolean) => api.setClientPerLine(client.cui, enabled),
    onSuccess: (saved, enabled) => {
      queryClient.setQueryData(['clients'], saved)
      toast.success(
        enabled
          ? 'De acum, fiecare linie primește contul ei. Facturile care au deja un cont rămân cum sunt.'
          : 'De acum, linia cea mai mare hotărăște contul facturii. Facturile care au deja un cont rămân cum sunt.',
      )
    },
    onError: showError,
  })
  // While the answer is on its way the switch already stands where it was turned to.
  const on = turn.isPending ? turn.variables === true : client.per_line

  return (
    <section aria-labelledby="per-line-title" className="flex flex-wrap items-center gap-x-5 gap-y-2.5 rounded-2xl border bg-card px-5 py-3.5">
      <Switch
        checked={on}
        aria-labelledby="per-line-title"
        aria-describedby="per-line-text"
        aria-busy={turn.isPending}
        // Not disabled while the request is on its way: a disabled switch drops the keyboard focus.
        onCheckedChange={(wanted) => {
          if (!turn.isPending) turn.mutate(wanted)
        }}
      />
      <div className="min-w-0 flex-[1_1_420px]">
        <h2 id="per-line-title" className="font-sans text-lg font-bold">Clasificare pe fiecare linie</h2>
        <p id="per-line-text" className="text-muted-foreground">
          Fiecare linie a unei facturi primește contul ei, din reguli sau de la Jev. Oprit: linia cu valoarea cea mai
          mare hotărăște un singur cont pentru toată factura, ca până acum.
        </p>
      </div>
    </section>
  )
}
