import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api'
import { showError } from '../errorMessages'
import type { Invoice, RuleSuggestion } from '../types'
import { reloadWhatARuleChanges } from './proposedRule'
import { ProposedRuleCardBody } from './ProposedRuleCardBody'

/**
 * On an invoice no rule decided: the rule that would have chosen its account. "Nu acum" is
 * remembered, so no rule is proposed for this invoice again.
 */
export function ProposedRuleCard({ invoice, suggestion }: { invoice: Invoice; suggestion: RuleSuggestion }) {
  const queryClient = useQueryClient()
  // The card stays busy until the invoice has been read again and it is gone.
  const turnDown = useMutation({
    mutationFn: () => api.turnDownProposal([invoice.id]),
    onSuccess: () => reloadWhatARuleChanges(queryClient),
    onError: showError,
  })
  return (
    <ProposedRuleCardBody
      suggestion={suggestion}
      chosenBy={invoice.classification_method === 'jev' ? 'jev' : 'person'}
      onNotNow={() => turnDown.mutateAsync().catch(() => undefined)}
    />
  )
}
