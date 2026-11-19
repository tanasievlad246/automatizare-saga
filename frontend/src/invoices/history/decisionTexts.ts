// The words of the tab "Cum s-a ales contul": each change of an invoice's account, when and how
// it happened, and for each line (or the whole invoice) the account and why.

import { countOf, formatPercent } from '../../format'
import { matchWords } from '../../rules/test/ruleReason'
import type { Decision, DecisionSource, LineMethod } from '../../types'
import { misfitReason } from '../issuedInvoices'
import { whyWaiting } from '../lineAccounts'

export const HISTORY_TAB = 'Cum s-a ales contul'
export const EMPTY_HISTORY =
  'Încă nu este nimic aici. Istoricul se ține de la versiunea 0.14.0: contul ales înainte se vede în cartonaș, dar nu și cum s-a ajuns la el.'
export const JEV_ODDS = 'Cât de potrivit i-a părut fiecare cont'
export const FOLD_AFTER = 6 // rows of one moment shown before "Arată toate"

/** How the account changed, at the head of a moment. */
export function sourceLabel(source: DecisionSource, jevOnly: boolean): string {
  switch (source) {
    case 'download':
      return 'La descărcare'
    case 'again':
      return 'Clasificată din nou'
    case 'redecide':
      return jevOnly ? 'Hotărâtă din nou: doar Jev' : 'Hotărâtă din nou: regulile, apoi Jev'
    case 'person':
      return 'Ales de dumneavoastră'
    case 'split':
      return 'Împărțită pe linii de dumneavoastră'
  }
}

/** Why the line (or the invoice, with `line` null) has its account, or why it waits: the words after the account. */
export function decisionSentence({ line, cont, method, reason, said }: Decision): string {
  const sure = (confidence: number | null) => formatPercent(confidence)
  const level = said.confidence_threshold === null ? '' : ` (pragul este ${sure(said.confidence_threshold)})`
  if (!cont) {
    if (method === 'follows') return 'primește contul liniei celei mai mari, după ce îl alegeți'
    if (said.suggested_cont) {
      return said.confidence === null
        ? `Jev propune ${said.suggested_cont}, fără să spună cât de sigur este`
        : `Jev propune ${said.suggested_cont}, sigur doar ${sure(said.confidence)}${level}`
    }
    return whyWaiting(reason) ?? misfitReason(reason) ?? 'nimeni nu a putut alege contul'
  }
  switch (method) {
    case 'rules':
      return said.rule
        ? `regula „${said.rule}”${said.match ? matchWords(said.match, line === null ? 'largest' : 'line') : ''}`
        : 'după o regulă a dumneavoastră'
    case 'jev':
      return `ales de Jev, sigur ${sure(said.confidence)}${level}`
    case 'jev_accepted':
      return `propus de Jev${said.confidence === null ? '' : ` (sigur ${sure(said.confidence)})`}, acceptat de dumneavoastră`
    case 'follows':
      return 'ca linia cea mai mare'
    case 'invoice':
      return 'contul facturii, păstrat la împărțire'
    default:
      return 'ales de dumneavoastră'
  }
}

const BEFORE: Record<LineMethod, (rule: string | null) => string> = {
  rules: (rule) => (rule ? `, după regula „${rule}”` : ', după o regulă'),
  jev: () => ', ales de Jev',
  jev_accepted: () => ', propus de Jev',
  human: () => ', ales de dumneavoastră',
  follows: () => ', ca linia cea mai mare',
  invoice: () => ', contul facturii',
}

/** What the line had before this change; null when nothing was decided before. */
export function beforeText({ said }: Decision): string | null {
  const before = said.before
  if (!before) return null
  if (!before.cont) return 'înainte: de verificat'
  return `înainte: ${before.cont}${before.method ? BEFORE[before.method](before.rule) : ''}`
}

/** One row of a moment: one line, the whole invoice, or lines that got the same thing. */
export type HistoryRow = {
  key: string
  lines: number[] | null // null: the whole invoice
  cont: string | null // null: it waits for a person
  text: string
  before: string | null
  odds: { probabilities: Record<string, number>; choice: string | null } | null // what Jev said of each account
}

/** One change: when, how, and the rows it wrote. */
export type Moment = { key: string; at: string; label: string; rows: HistoryRow[]; lineCount: number }

/** The history as the tab shows it: the newest change first, each change's lines in order. */
export function moments(decisions: Decision[]): Moment[] {
  const found: { key: string; decisions: Decision[] }[] = []
  for (const decision of decisions) {
    const key = `${decision.at}|${decision.source}|${decision.said.jev_only}`
    if (found.at(-1)?.key === key) found.at(-1)!.decisions.push(decision)
    else found.push({ key, decisions: [decision] })
  }
  return found.map(({ key, decisions: theirs }) => {
    const [first] = theirs
    const rows: HistoryRow[] = []
    for (const decision of [...theirs].sort((one, other) => (one.line ?? 0) - (other.line ?? 0))) {
      const row = rowOf(decision)
      const same = decision.line === null ? undefined : rows.find(
        (other) => other.lines !== null && other.cont === row.cont && other.text === row.text && other.before === row.before && !other.odds && !row.odds,
      )
      if (same) same.lines!.push(decision.line!)
      else rows.push(row)
    }
    return {
      key, at: first.at, label: sourceLabel(first.source, first.said.jev_only), rows,
      lineCount: rows.reduce((count, row) => count + (row.lines?.length ?? 1), 0),
    }
  })
}

function rowOf(decision: Decision): HistoryRow {
  const { probabilities } = decision.said
  const asked = probabilities !== null && Object.keys(probabilities).length > 0
  return {
    key: String(decision.id),
    lines: decision.line === null ? null : [decision.line],
    cont: decision.cont,
    text: decisionSentence(decision),
    before: beforeText(decision),
    odds: asked ? { probabilities: probabilities!, choice: decision.cont ?? decision.said.suggested_cont } : null,
  }
}

/** "Factura", "Linia 3 · Cafea boabe 1 kg", "Liniile 2 și 3". */
export function rowLabel(lines: number[] | null, names: Record<number, string>): string {
  if (lines === null) return 'Factura'
  if (lines.length === 1) return `Linia ${lines[0]}${names[lines[0]] ? ` · ${names[lines[0]]}` : ''}`
  return `Liniile ${lines.length === 2 ? lines.join(' și ') : `${lines.slice(0, -1).join(', ')} și ${lines.at(-1)}`}`
}

/** Under a long moment, folded after FOLD_AFTER rows. */
export function showAllLabel(lines: number): string {
  return `Arată toate cele ${countOf(lines, '', 'linii')}`
}
