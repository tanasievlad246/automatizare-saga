import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import type { RuleFields } from '../types'
import { shownOutOf } from './proposedRule'
import { ProposedRuleRow } from './ProposedRuleRow'

/** On the rules screen: rules worth creating from what Jev and the person decided lately. */
export function ProposedRulesSection({ onChangeFirst }: { onChangeFirst: (draft: RuleFields) => void }) {
  const { data } = useQuery({ queryKey: ['proposed-rules'], queryFn: api.proposedRules })
  if (!data || data.count === 0) return null

  return (
    <section aria-label="Reguli propuse" className="flex flex-col gap-3.5 rounded-2xl bg-fresh p-5">
      <div>
        <h2 className="text-2xl text-fresh-foreground">Reguli propuse</h2>
        <p className="mt-1 max-w-3xl">
          Pentru aceste facturi nu s-a potrivit nicio regulă, așa că a ales Jev sau ați ales dumneavoastră. Cu o
          regulă, data viitoare contul se pune singur.
        </p>
      </div>
      {data.suggestions.map((proposal) => (
        <ProposedRuleRow
          key={[proposal.cont, ...proposal.keywords, ...proposal.supplier_cuis].join('|')}
          proposal={proposal}
          days={data.days}
          onChangeFirst={onChangeFirst}
        />
      ))}
      {data.count > data.suggestions.length && (
        <p>{shownOutOf(data.suggestions.length, data.count)} Celelalte apar pe măsură ce le rezolvați pe acestea.</p>
      )}
    </section>
  )
}
