import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Notice } from '@/components/Notice'
import { PageTitle } from '@/components/PageTitle'
import { PillTabs } from '@/components/PillTabs'
import { Button } from '@/components/ui/button'
import { api } from '../api'
import { errorMessage, showError } from '../errorMessages'
import { kindFrom } from '../invoices/issuedInvoices'
import type { InvoiceKind, Rule, RuleFields } from '../types'
import { AccountsCard } from './AccountsCard'
import { JevSettingsCard } from './JevSettingsCard'
import { ProposedRulesSection } from './ProposedRulesSection'
import { RuleDialog } from './RuleDialog'
import { RuleRow } from './RuleRow'

const KINDS: { value: InvoiceKind; label: string }[] = [
  { value: 'received', label: 'Pentru facturile primite' },
  { value: 'issued', label: 'Pentru facturile emise' },
]

/**
 * Everything that decides an invoice's account: the rules, Jev's accounts, how sure Jev must be,
 * the questions Jev is asked. Each kind of invoice, received or issued, has its own tab: a rule,
 * an account or a question is for one kind only. How sure Jev must be is one setting for both.
 */
export function RulesPage() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useSearchParams()
  const kind = kindFrom(search)
  const { data, error } = useQuery({ queryKey: ['rules'], queryFn: api.rules })
  const rules = data?.rules.filter((rule) => rule.direction === kind) ?? []
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

      <PillTabs
        label="Pentru ce facturi"
        options={KINDS}
        value={kind}
        onChange={(wanted) => setSearch(wanted === 'issued' ? { fel: 'emise' } : {}, { replace: true })}
      />

      {/* Proposed rules come from received invoices only, so far. */}
      {kind === 'received' && <ProposedRulesSection onChangeFirst={(draft) => setEditing({ rule: 'new', draft })} />}

      <section className="flex flex-col gap-3.5">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
          <div className="min-w-0 flex-[1_1_240px]">
            <h2 className="text-2xl">{kind === 'issued' ? 'Regulile pentru facturile emise' : 'Regulile mele'}</h2>
            {kind === 'issued' && (
              <p className="mt-1 text-muted-foreground">
                Se uită la liniile facturilor emise de clienți: cuvinte, codul articolului, codul CPV sau NC. Nu se
                uită la cumpărător. O regulă de aici nu hotărăște niciodată o factură primită.
              </p>
            )}
          </div>
          <Button onClick={() => setEditing({ rule: 'new' })}>Adaugă o regulă</Button>
        </div>
        {data && rules.length === 0 && (
          <p className="rounded-2xl border bg-card px-6 py-6 text-lg">
            {kind === 'issued'
              ? 'Nicio regulă pentru facturile emise încă. Fără reguli, liniile lor merg la Jev.'
              : 'Nicio regulă încă. Fără reguli, toate facturile merg la Jev.'}
          </p>
        )}
        {rules.map((rule, index) => (
          <RuleRow
            key={rule.id}
            rule={rule}
            position={index + 1}
            isLast={index === rules.length - 1}
            clientName={clients.find((client) => client.cui === rule.client_cui)?.name ?? null}
            onEdit={() => setEditing({ rule })}
            onMove={(up) => move.mutate({ id: rule.id, up })}
          />
        ))}
      </section>

      {data && <AccountsCard kind={kind} accounts={kind === 'issued' ? data.issued_accounts : data.accounts} />}
      {data && (
        <JevSettingsCard
          // The fields start from the questions of the tab shown.
          key={kind}
          kind={kind}
          minConfidence={data.min_confidence}
          question={kind === 'issued' ? data.jev_issued_instructions : data.jev_instructions}
          lineQuestion={kind === 'issued' ? data.jev_issued_line_instructions : data.jev_line_instructions}
        />
      )}
      {editing && <RuleDialog {...editing} kind={kind} clients={clients} onClose={() => setEditing(null)} />}
    </div>
  )
}
