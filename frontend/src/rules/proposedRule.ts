import type { QueryClient } from '@tanstack/react-query'
import { countOf } from '../format'
import type { ProposedRule, RuleFields } from '../types'

/** What a proposal needs to become a rule: the account, and words or a supplier to look for. */
export type Proposal = Pick<ProposedRule, 'cont' | 'keywords' | 'supplier_cuis' | 'supplier_name'>

/** The rule a proposal turns into: for every client, switched on, named after what it looks for. */
export function ruleFromProposal(proposal: Proposal): RuleFields {
  const forSupplier = proposal.supplier_cuis.length > 0
  const supplier = proposal.supplier_name || `furnizor ${proposal.supplier_cuis.join(', ')}`
  return {
    name: proposal.keywords.join(', ') || (forSupplier ? supplier : ''),
    cont: proposal.cont,
    keywords: proposal.keywords,
    supplier_cuis: proposal.supplier_cuis,
    item_codes: [],
    commodity_prefixes: [],
    client_cui: null,
    enabled: true,
    direction: 'received', // proposed rules come from received invoices only, so far
  }
}

/** What the proposal looks for, as the rest of a sentence that starts with "Dacă". */
export function conditionInWords(proposal: Proposal): string {
  if (proposal.keywords.length > 0) return `pe factură scrie: ${proposal.keywords.join(', ')}`
  return proposal.supplier_name
    ? `factura este de la ${proposal.supplier_name}`
    : `furnizorul are CUI ${proposal.supplier_cuis.join(', ')}`
}

/** "Sunt afișate primele 20 din 21 de propuneri.": under a list that does not show them all. */
export function shownOutOf(shown: number, total: number): string {
  return `Sunt afișate primele ${shown} din ${countOf(total, 'o propunere', 'propuneri')}.`
}

// Every list the page keeps that a new, changed or turned-down rule can change.
const LISTS_A_RULE_CHANGES = ['rules', 'proposed-rules', 'invoice']

/**
 * Reads those lists again; done when they have all arrived. Returned from an action's
 * onSuccess, it keeps the button busy until the proposal has left the screen, so a second
 * press cannot create the same rule twice.
 */
export function reloadWhatARuleChanges(queryClient: QueryClient): Promise<unknown> {
  return Promise.all(LISTS_A_RULE_CHANGES.map((key) => queryClient.invalidateQueries({ queryKey: [key] })))
}
