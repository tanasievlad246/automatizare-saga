import { formatPercent, formatUsd } from '../../format'
import { formatDuration } from '../../journal/eventTexts'
import type { TrialAsk, TrialJev, TrialLineAnswer } from '../../types'
import { ruleReason } from './ruleReason'

export type LineSaid = {
  tone: 'done' | 'attention'
  heading: string // "Contul 6022", "De verificat", "Jev nu a putut fi întrebat."
  headingNote: string | null // what the account is for, or what Jev proposed
  chip: { kind: 'rule' | 'jev' | 'follows' | 'waiting'; text: string } | null
  sentence: string // why
  notes: string[] // what else is worth knowing, in smaller type
  technical: string | null
  jevShown: boolean // whether "Ce a spus Jev" is offered under the line
}

export type LineContext = {
  ask: TrialAsk
  clientName?: string
  // One account for the whole invoice: the line stands for it, and the words say "factură".
  wholeInvoice?: boolean
  // The line whose question OpenRouter failed on as a whole; nothing was sent after it.
  stoppedAt?: number
}

// OpenRouter turned the key away (401, 403) or the account has no credit left (402): waiting does not help.
const REFUSED_BY_OPENROUTER = [401, 402, 403]
export const REFUSED_SENTENCE = 'OpenRouter a refuzat întrebarea. Verificați cheia OpenRouter și creditul din cont.'
export const NO_ANSWER_SENTENCE = 'Jev nu a răspuns. Încercați din nou puțin mai târziu.'
const NOT_ASKED = 'Jev nu a fost întrebat pentru această linie.'

/** "A costat < 0,01 $ și a durat 1,4 s.", or what of it is known; null when neither is. */
export function spentOnJev(jev: TrialJev): string | null {
  const parts = [
    jev.cost_usd === null ? null : `a costat ${formatUsd(jev.cost_usd)}`,
    jev.duration_ms === null ? null : `a durat ${formatDuration(jev.duration_ms)}`,
  ].filter((part) => part !== null)
  const said = parts.join(' și ')
  return said ? `${said[0].toUpperCase()}${said.slice(1)}.` : null
}

/** Did OpenRouter refuse the question in a way that waiting does not help? */
export function refusedByOpenRouter(jev: TrialJev | null): boolean {
  return jev?.http_status != null && REFUSED_BY_OPENROUTER.includes(jev.http_status)
}

/** What the screen says about one line of the trial invoice: its account, who gave it and why. */
export function describeLine(entry: TrialLineAnswer, context: LineContext): LineSaid {
  const { jev } = entry
  const percent = formatPercent
  const here = context.wholeInvoice ? 'această factură' : 'această linie'
  const before = context.ask === 'jev_only' ? 'Regulile au fost sărite, cum ați cerut.' : 'Nicio regulă nu s-a potrivit.'
  const account = { heading: `Contul ${entry.cont}`, headingNote: entry.account_description }
  const waiting = { tone: 'attention' as const, heading: 'De verificat', headingNote: null, chip: null, notes: [], technical: null, jevShown: false }

  if (entry.decided_by === 'rule' && entry.rule) {
    const [sentence, ...notes] = ruleReason(entry.rule, context.clientName)
    return {
      tone: 'done', ...account, chip: { kind: 'rule', text: 'Ales de o regulă' }, sentence,
      notes: [...notes, context.wholeInvoice ? 'Jev nu a fost întrebat pentru această factură.' : NOT_ASKED],
      technical: null, jevShown: false,
    }
  }

  if (entry.decided_by === 'follows') {
    const value = Number(entry.value)
    const why = value === 0 ? 'Linia are valoarea 0' : value < 0 ? 'Este o reducere' : 'Are semnul opus liniei cele mai mari'
    const sentence = `${why}, deci primește contul liniei ${entry.follows}, cea mai mare de pe factură.`
    const chip = { kind: 'follows' as const, text: `Ca linia ${entry.follows}` }
    if (!entry.cont) {
      return { ...waiting, chip, sentence, notes: [`Linia ${entry.follows} nu are încă un cont, deci nici aceasta.`] }
    }
    return { tone: 'done', ...account, chip, sentence, notes: [NOT_ASKED], technical: null, jevShown: false }
  }

  if (entry.same_as !== null) {
    // Said as for the line Jev was asked about, with the reason folded into a note.
    const asFirst = describeLine({ ...entry, same_as: null }, context)
    return {
      ...asFirst, jevShown: false,
      sentence: `La fel ca linia ${entry.same_as}: scrie același lucru, deci Jev a fost întrebat o singură dată pentru amândouă.`,
      notes: asFirst.chip?.kind === 'jev' ? [] : [asFirst.sentence],
    }
  }

  if (entry.decided_by === 'jev' && jev) {
    return {
      tone: 'done', ...account, chip: { kind: 'jev', text: 'Ales de Jev' }, notes: [], technical: null, jevShown: true,
      sentence: `${before} Jev este sigur ${percent(jev.confidence)}, iar pragul dumneavoastră este ${percent(jev.threshold)}, deci ${context.wholeInvoice ? 'factura' : 'linia'} primește contul.`,
    }
  }

  if (entry.why_not === 'below_threshold' && jev) {
    return {
      ...waiting, headingNote: `Jev propune contul ${jev.choice}`, chip: { kind: 'waiting', text: 'Sub prag' }, jevShown: true,
      sentence: `${before} Jev este sigur doar ${percent(jev.confidence)}, sub pragul dumneavoastră de ${percent(jev.threshold)}.`,
    }
  }

  if (entry.why_not === 'jev_declined' && jev) {
    if (jev.refused) {
      return {
        ...waiting, headingNote: 'Jev a refuzat', jevShown: true,
        sentence: `Jev a refuzat să răspundă la întrebarea despre ${here}.`,
        notes: ['Când refuză, Jev nu trimite nimic altceva: niciun cont și nicio cifră despre cât de potrivit i se pare vreunul.'],
      }
    }
    if (jev.choice === null) {
      return {
        ...waiting, headingNote: 'niciun cont din listă', jevShown: true,
        sentence: `Jev crede că niciun cont din lista dumneavoastră nu se potrivește cu ce s-a cumpărat pe ${here}.`,
        notes: ['Jev alege după descrierea conturilor. Dacă un cont ar trebui să se potrivească, scrieți-i descrierea mai clar sau adăugați contul la „Reguli de clasificare”.'],
      }
    }
    return {
      ...waiting, headingNote: `Jev propune contul ${jev.choice}`, jevShown: true,
      sentence: `Jev a ales contul ${jev.choice}, dar nu a spus cât de sigur este. Fără această cifră, programul nu dă contul singur.`,
    }
  }

  if (entry.why_not === 'jev_failed') {
    const sentence = !jev
      ? `${context.wholeInvoice ? 'Factura' : 'Linia'} și lista de conturi nu încap într-o singură întrebare pentru Jev.`
      : refusedByOpenRouter(jev) ? REFUSED_SENTENCE : NO_ANSWER_SENTENCE
    return { ...waiting, heading: 'Jev nu a putut fi întrebat.', sentence, technical: jev?.error ?? entry.reason }
  }

  if (entry.why_not === 'not_asked') {
    const earlier = context.stoppedAt ? `întrebarea despre linia ${context.stoppedAt}` : 'o întrebare de mai sus'
    return { ...waiting, sentence: `Nu a mai fost trimisă lui Jev, pentru că ${earlier} nu a reușit.` }
  }

  // No key or no accounts: the answer above the lines says which, once.
  const skipped = context.ask === 'jev_only' ? 'Regulile au fost sărite' : 'Nicio regulă nu s-a potrivit'
  return { ...waiting, sentence: `${skipped}, iar Jev nu a putut fi întrebat.` }
}
