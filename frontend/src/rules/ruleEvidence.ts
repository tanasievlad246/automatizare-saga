import { countOf } from '../format'
import type { RuleEvidence } from '../types'

export type EvidenceTone = 'agrees' | 'differs' | 'none'

/**
 * How a rule would have done on the invoices of the last `days` days, in one sentence.
 * It agrees when every invoice it matches is already on the account the rule would give.
 */
export function describeEvidence(
  evidence: RuleEvidence, cont: string, days: number,
): { text: string; tone: EvidenceTone } {
  const lately = `din ultimele ${countOf(days, 'zi', 'zile')}`
  if (evidence.matches === 0) {
    return { text: `Nu s-ar fi potrivit la nicio factură ${lately}.`, tone: 'none' }
  }
  const matched = `S-ar fi potrivit la ${countOf(evidence.matches, 'o factură', 'facturi')} ${lately}`
  // The account of the rule first, then the others, the one with most invoices first.
  const accounts = Object.entries(evidence.by_cont).sort(
    ([a, countA], [b, countB]) => Number(b === cont) - Number(a === cont) || countB - countA,
  )
  if (accounts.length === 1) {
    const [account] = accounts[0]
    const all = evidence.matches === 1 ? '' : evidence.matches === 2 ? 'amândouă ' : 'toate '
    return { text: `${matched}, ${all}pe contul ${account}.`, tone: account === cont ? 'agrees' : 'differs' }
  }
  const each = accounts.map(([account, count]) => `${count === 1 ? 'una' : count} pe contul ${account}`)
  return { text: `${matched}: ${each.slice(0, -1).join(', ')} și ${each.at(-1)}.`, tone: 'differs' }
}
