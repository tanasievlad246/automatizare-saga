import { formatPercent, formatUsd } from '../../format'
import { formatDuration } from '../../journal/eventTexts'
import type { RuleTestResult, TrialAsk } from '../../types'

export type DescribedAnswer = {
  tone: 'done' | 'attention'
  title: string
  subtitle: string
  label: string | null
  sentences: string[]
  technical: string | null
}

const REASONS_NOBODY_WAS_ASKED: Record<string, string[]> = {
  no_lines: ['Factura de probă nu are niciun rând.'],
  no_key: [
    'Lipsește cheia OpenRouter. O scrieți la „Chei și parole”.',
    'Regulile se pot încerca și fără cheie: dacă o regulă se potrivește, răspunsul vine de la ea.',
  ],
  no_accounts: ['Nu există niciun cont din care Jev să aleagă. Le adăugați la „Reguli de clasificare”.'],
  jev_failed: ['Jev nu a răspuns. Încercați din nou puțin mai târziu.'],
}
// OpenRouter turned the key away (401, 403) or the account has no credit left (402): waiting does not help.
const REFUSED_BY_OPENROUTER = [401, 402, 403]
const REFUSED_SENTENCES = ['OpenRouter a refuzat întrebarea. Verificați cheia OpenRouter și creditul din cont.']

/**
 * What the screen says about the program's answer. What to say comes from `why_not`, not from
 * whether `jev` is there: a request too large to send has no `jev` and still failed.
 */
export function describeAnswer(result: RuleTestResult, ask: TrialAsk): DescribedAnswer {
  const { jev } = result
  const percent = formatPercent

  if (result.decided_by === 'rule') {
    return {
      tone: 'done', title: `Contul ${result.cont}`, subtitle: result.account_description ?? '', label: 'Ales de o regulă', technical: null,
      sentences: [
        `Regula dumneavoastră „${result.rule?.name}”, pentru rândul „${result.deciding_line}”.`,
        'Jev nu a fost întrebat, deci nu a costat nimic.',
      ],
    }
  }

  if (result.decided_by === 'jev' && jev) {
    const others = Object.entries(jev.probabilities)
      .filter(([cont, share]) => cont !== result.cont && share > 0)
      .sort((a, b) => b[1] - a[1])
      .map(([cont, share]) => `${cont} (${percent(share)})`)
    const spent = [
      jev.cost_usd === null ? null : `a costat ${formatUsd(jev.cost_usd)}`,
      jev.duration_ms === null ? null : `a durat ${formatDuration(jev.duration_ms)}`,
    ].filter((part) => part !== null)
    const spentSentence = spent.join(' și ')
    return {
      tone: 'done', title: `Contul ${result.cont}`, subtitle: result.account_description ?? '', label: 'Ales de Jev', technical: null,
      sentences: [
        ask === 'jev_only' ? 'Regulile au fost sărite.' : 'Nicio regulă nu s-a potrivit, așa că a fost întrebat Jev.',
        `Cât de sigur este: ${percent(jev.confidence)}. Pragul dumneavoastră este ${percent(jev.threshold)}, deci o factură adevărată ar fi primit contul fără să vă mai întrebe.`,
        ...(others.length > 0 ? [`S-a gândit și la: ${others.join(', ')}.`] : []),
        ...(spentSentence ? [`${spentSentence[0].toUpperCase()}${spentSentence.slice(1)}.`] : []),
      ],
    }
  }

  if (result.why_not === 'below_threshold' && jev) {
    return {
      tone: 'attention', title: 'De verificat', subtitle: `Jev propune contul ${jev.choice}`, label: null, technical: null,
      sentences: [
        `Jev este sigur doar ${percent(jev.confidence)}, sub pragul dumneavoastră de ${percent(jev.threshold)}.`,
        'O factură adevărată ar aștepta la „De verificat” până îi alegeți dumneavoastră contul.',
      ],
    }
  }

  if (result.why_not === 'jev_declined') {
    return {
      tone: 'attention', title: 'De verificat', subtitle: 'Jev nu a ales niciun cont pentru această factură.', label: null,
      sentences: [], technical: null,
    }
  }

  const refused = result.why_not === 'jev_failed' && jev?.http_status != null && REFUSED_BY_OPENROUTER.includes(jev.http_status)
  return {
    tone: 'attention', title: 'Jev nu a putut fi întrebat.', subtitle: '', label: null,
    sentences: refused ? REFUSED_SENTENCES : (REASONS_NOBODY_WAS_ASKED[result.why_not ?? ''] ?? []),
    technical: result.why_not === 'jev_failed' ? (jev?.error ?? result.reason) : null,
  }
}
