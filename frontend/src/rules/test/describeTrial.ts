import { countOf, formatUsd } from '../../format'
import type { RuleTestResult, TrialAsk, TrialLineAnswer } from '../../types'
import { NO_ANSWER_SENTENCE, REFUSED_SENTENCE, refusedByOpenRouter, spentOnJev } from './describeLine'

export type TrialSaid = {
  tone: 'done' | 'attention'
  failed: boolean // Jev could not be asked at all: the box carries a warning sign
  title: string
  subtitle: string
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
}
const NOT_ASKED = 'Jev nu a fost întrebat, deci nu a costat nimic.'
const WAITS = 'O factură adevărată ar aștepta la „De verificat” până îi alegeți dumneavoastră contul.'
const RULES_SKIPPED = 'Regulile au fost sărite. O factură adevărată ar trece întâi prin reguli, deci ar putea primi alt cont.'

/**
 * What the answer says above the lines: whether the invoice would get its accounts by
 * itself, which lines wait, and what asking Jev cost. Each line then says its own why.
 * `linesOnInvoice` is how many lines the trial invoice has; with one account per invoice the
 * answer holds only the line that decides.
 */
export function describeTrial(result: RuleTestResult, linesOnInvoice: number, ask: TrialAsk): TrialSaid {
  return result.per_line ? byLines(result, ask) : whole(result, linesOnInvoice, ask)
}

function byLines(result: RuleTestResult, ask: TrialAsk): TrialSaid {
  const { lines } = result
  const waiting = lines.filter((entry) => !entry.cont)
  const asked = lines.filter((entry) => entry.jev && entry.same_as === null).map((entry) => entry.line)
  const cost = result.cost_usd === null
    ? ''
    : result.cost_usd === 0 ? ' Nu a costat nimic.' : ` A costat ${formatUsd(result.cost_usd)}${asked.length > 1 ? ' în total' : ''}.`
  const costSentence = result.jev_calls === 0
    ? NOT_ASKED
    : result.jev_calls === 1
      ? `Jev a fost întrebat o dată, pentru linia ${asked[0]}.${cost}`
      : `Jev a fost întrebat de ${countOf(result.jev_calls, '', 'ori')}, câte o dată pentru liniile ${numbers(asked)}.${cost}`

  if (waiting.length === 0) {
    const accounts = [...new Set(lines.map((entry) => entry.cont))]
    return {
      tone: 'done', failed: false, title: 'Toate liniile au cont', technical: null,
      subtitle: accounts.length === 1 ? `Contul ${accounts[0]}` : `Conturile ${numbers(accounts as string[])}`,
      sentences: [ask === 'jev_only' ? RULES_SKIPPED : 'O factură adevărată ar primi aceste conturi fără să vă mai întrebe.', costSentence],
    }
  }

  const have = lines.length - waiting.length
  const subtitle = have === 0 ? 'Nicio linie nu are cont' : `${countOf(have, 'o linie are', 'linii au')} cont, ${waitingWords(waiting)} așteaptă`
  const stopped = result.jev_stopped
  if (stopped) {
    // As the program does when OpenRouter fails as a whole: the invoice waits and Jev is asked again later.
    const failedLine = lines.find((entry) => entry.line === stopped.line)
    const leftOut = lines.some((entry) => entry.why_not === 'not_asked') ? ', așa că celelalte linii nu au mai fost trimise' : ''
    return {
      tone: 'attention', failed: true, title: 'Jev nu a putut fi întrebat.', subtitle, technical: stopped.error,
      sentences: [
        refusedByOpenRouter(failedLine?.jev ?? null) ? REFUSED_SENTENCE : NO_ANSWER_SENTENCE,
        `Întrebarea despre linia ${stopped.line} nu a reușit${leftOut}. O factură adevărată ar rămâne în așteptare, iar Jev ar fi întrebat din nou la următoarea descărcare.`,
        costSentence,
      ],
    }
  }
  // A discount waiting for the largest line is settled with it, so it is not one to choose for.
  const toChoose = waiting.filter((entry) => entry.decided_by !== 'follows')
  const choose = (toChoose.length > 0 ? toChoose : waiting).map((entry) => entry.line)
  const whose = choose.length === 1 ? `liniei ${choose[0]}` : `liniilor ${numbers(choose)}`
  const notAsked = [...new Set(waiting.map((entry) => entry.why_not))].flatMap((why) => (why === 'no_key' || why === 'no_accounts' ? REASONS_NOBODY_WAS_ASKED[why] : []))
  return {
    tone: 'attention', failed: false, title: 'De verificat', technical: null,
    subtitle,
    sentences: [
      `O factură adevărată ar aștepta la „De verificat” până alegeți contul ${whose}.${have > 0 ? ' Celelalte linii își păstrează contul.' : ''}`,
      ...notAsked,
      costSentence,
    ],
  }
}

function whole(result: RuleTestResult, linesOnInvoice: number, ask: TrialAsk): TrialSaid {
  const { jev } = result
  const decidedBy = linesOnInvoice > 1 && result.deciding_line
    ? [`Clientul are un singur cont pe factură: s-a hotărât după linia „${result.deciding_line}”, cea cu valoarea cea mai mare.`]
    : []
  const spent = jev ? spentOnJev(jev) : NOT_ASKED
  const costSentence = spent ? [spent] : []

  if (result.cont) {
    return {
      tone: 'done', failed: false, title: `Contul ${result.cont}`, subtitle: result.account_description ?? '', technical: null,
      sentences: [
        ...decidedBy,
        ...(ask === 'jev_only' ? [RULES_SKIPPED] : result.decided_by === 'jev' ? ['O factură adevărată ar primi contul fără să vă mai întrebe.'] : []),
        ...costSentence,
      ],
    }
  }
  if (result.why_not === 'below_threshold' && jev) {
    return { tone: 'attention', failed: false, title: 'De verificat', subtitle: `Jev propune contul ${jev.choice}`, technical: null, sentences: [...decidedBy, WAITS, ...costSentence] }
  }
  if (result.why_not === 'jev_declined' && jev) {
    const subtitle = jev.refused
      ? 'Jev a refuzat să răspundă'
      : jev.choice === null ? 'Jev nu a ales niciun cont din listă' : `Jev propune contul ${jev.choice}, fără să spună cât de sigur este`
    return { tone: 'attention', failed: false, title: 'De verificat', subtitle, technical: null, sentences: [...decidedBy, WAITS, ...costSentence] }
  }

  const failedSentences = result.why_not !== 'jev_failed'
    ? (REASONS_NOBODY_WAS_ASKED[result.why_not ?? ''] ?? [])
    : !jev
      ? ['Factura și lista de conturi nu încap într-o singură întrebare pentru Jev.']
      : [refusedByOpenRouter(jev) ? REFUSED_SENTENCE : NO_ANSWER_SENTENCE]
  return {
    tone: 'attention', failed: true, title: 'Jev nu a putut fi întrebat.', subtitle: '', sentences: failedSentences,
    technical: result.why_not === 'jev_failed' ? (jev?.error ?? result.reason) : null,
  }
}

/** "3", "2 și 3", "1, 2 și 5". */
function numbers(items: (string | number)[]): string {
  const said = items.map(String)
  return said.length < 2 ? said.join('') : `${said.slice(0, -1).join(', ')} și ${said.at(-1)}`
}

/** "linia 3", "liniile 3 și 5". */
function waitingWords(waiting: TrialLineAnswer[]): string {
  const lines = waiting.map((entry) => entry.line)
  return lines.length === 1 ? `linia ${lines[0]}` : `liniile ${numbers(lines)}`
}
