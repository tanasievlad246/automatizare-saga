import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'
import { Notice } from '@/components/Notice'
import { PageTitle } from '@/components/PageTitle'
import { Button } from '@/components/ui/button'
import { api } from '../api'
import { errorMessage, showError } from '../errorMessages'
import type { Rule, RuleFields } from '../types'
import { AccountsCard } from './AccountsCard'
import { JevSettingsCard } from './JevSettingsCard'
import { ProposedRulesSection } from './ProposedRulesSection'
import { RuleDialog } from './RuleDialog'
import { RuleRow } from './RuleRow'

/** Everything that decides an invoice's account: the rules, Jev's accounts, how sure Jev must be. */
export function RulesPage() {
  const queryClient = useQueryClient()
  const { data, error } = useQuery({ queryKey: ['rules'], queryFn: api.rules })
  const clients = useQuery({ queryKey: ['clients'], queryFn: api.clients }).data?.clients ?? []
  // The rule in the window: an existing one, or a new one that may start from a proposal.
  const [editing, setEditing] = useState<{ rule: Rule | 'new'; draft?: RuleFields } | null>(null)
  const move = useMutation({
    mutationFn: ({ id, up }: { id: number; up: boolean }) => api.moveRule(id, up),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['rules'] }),
    onError: showError,
  })

  return (
    <div className="flex max-w-[66rem] flex-col gap-9">
      <div className="flex flex-wrap items-start gap-x-6 gap-y-3">
        <div className="min-w-0 flex-[1_1_28rem]">
          <PageTitle title="Reguli de clasificare">
            O regulă alege contul singură, fără Jev. Întâi se verifică regulile clientului, apoi cele pentru toți clienții, fiecare grup de sus în jos. Prima care se potrivește câștigă.
          </PageTitle>
        </div>
        <Button asChild variant="outline" size="lg"><Link to="/reguli/test">Testează regulile</Link></Button>
      </div>
      {error && <Notice tone="attention">{errorMessage(error)}</Notice>}

      <ProposedRulesSection onChangeFirst={(draft) => setEditing({ rule: 'new', draft })} />

      <section className="flex flex-col gap-3.5">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
          <h2 className="min-w-0 flex-[1_1_240px] text-2xl">Regulile mele</h2>
          <Button onClick={() => setEditing({ rule: 'new' })}>Adaugă o regulă</Button>
        </div>
        {data?.rules.length === 0 && (
          <p className="rounded-2xl border bg-card px-6 py-6 text-lg">
            Nicio regulă încă. Fără reguli, toate facturile merg la Jev.
          </p>
        )}
        {data?.rules.map((rule, index) => (
          <RuleRow
            key={rule.id}
            rule={rule}
            position={index + 1}
            isLast={index === data.rules.length - 1}
            clientName={clients.find((client) => client.cui === rule.client_cui)?.name ?? null}
            onEdit={() => setEditing({ rule })}
            onMove={(up) => move.mutate({ id: rule.id, up })}
          />
        ))}
      </section>

      {data && <AccountsCard accounts={data.accounts} />}
      {data && (
        <JevSettingsCard
          minConfidence={data.min_confidence}
          question={data.jev_instructions}
          lineQuestion={data.jev_line_instructions}
        />
      )}
      {editing && <RuleDialog {...editing} clients={clients} onClose={() => setEditing(null)} />}
    </div>
  )
}
