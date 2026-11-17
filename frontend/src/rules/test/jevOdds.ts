import { countOf } from '../../format'

// What Jev is offered beside the accounts, to say that none of them fits.
export const NONE_OF_THESE = 'altul'
// Below this an account is only counted, not drawn: Jev rarely leaves anything at exactly 0.
const SHOWN_FROM = 0.01

export type OddsRow = {
  key: string
  label: string // the account, or "Niciunul din listă"
  description: string | null // what belongs on the account, as the rules screen has it
  share: number
  chosen: boolean
  none: boolean
}

/**
 * How likely Jev found each account it was offered, from the most likely. Jev writes no
 * reasons: these figures are all it says about why. Accounts it found unlikely are counted
 * in one sentence, in the order the rules screen lists them.
 */
export function jevOdds(
  probabilities: Record<string, number>,
  accounts: Record<string, string>,
  choice: string | null,
): { rows: OddsRow[]; below: string | null } {
  if (Object.keys(probabilities).length === 0) return { rows: [], below: null }
  // Jev answering "none of these" has no account as its choice.
  const picked = choice ?? NONE_OF_THESE
  const rows = Object.entries(probabilities)
    .filter(([, share]) => share >= SHOWN_FROM)
    .sort((a, b) => b[1] - a[1])
    .map(([key, share]) => ({
      key,
      label: key === NONE_OF_THESE ? 'Niciunul din listă' : key,
      description: key === NONE_OF_THESE ? null : (accounts[key] ?? null),
      share,
      chosen: key === picked,
      none: key === NONE_OF_THESE,
    }))
  const unlikely = Object.keys(accounts)
    .filter((cont) => (probabilities[cont] ?? 0) < SHOWN_FROM)
    .sort((a, b) => a.localeCompare(b, 'ro', { numeric: true }))
  const below = unlikely.length === 0
    ? null
    : `${unlikely.length === 1 ? 'Celălalt cont' : `Celelalte ${countOf(unlikely.length, '', 'conturi')}`} (${unlikely.join(', ')}): sub 1%.`
  return { rows, below }
}
