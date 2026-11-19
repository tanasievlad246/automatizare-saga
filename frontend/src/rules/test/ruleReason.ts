import type { RuleMatch, TrialRule } from '../../types'

/** "„a”", "„a” și „b”", "„a”, „b” și „c”". */
export function quotedList(names: string[]): string {
  const quoted = names.map((name) => `„${name}”`)
  return quoted.length < 2 ? quoted.join('') : `${quoted.slice(0, -1).join(', ')} și ${quoted.at(-1)}`
}

/**
 * Why a rule gave a line its account, in the order the screen says it: which of its
 * conditions the line meets, then the rules further down that would have matched too, and
 * whether the rule is for one client only.
 */
export function ruleReason(rule: TrialRule, clientName?: string): string[] {
  const name = `Regula „${rule.name}”`
  const sentences = [`${name}${because(rule)}.`]
  if (rule.also.length > 0) {
    const others = rule.also.length === 1 ? 'regula' : 'regulile'
    sentences.push(`S-ar fi potrivit și ${others} ${quotedList(rule.also)}, dar „${rule.name}” este mai sus în listă.`)
  }
  if (rule.client_only) sentences.push(`Este o regulă doar pentru ${clientName || 'clientul ales'}.`)
  return sentences
}

function because(rule: TrialRule): string {
  return rule.condition ? matchWords({ ...rule, condition: rule.condition, found: rule.found ?? '' }) : ''
}

/** What a rule found, as `matchWords` reads it: the condition and the words or code. */
type Found = Pick<RuleMatch, 'condition' | 'found' | 'prefix'> & { matched?: string | null; in_details?: boolean }

/**
 * Which condition of a rule a line meets, and with what, after the rule's name:
 * ": pe linie scrie „motorina”, unul din cuvintele regulii". `on` 'largest': the line is the
 * largest of an invoice with one account.
 */
export function matchWords({ condition, found, prefix, matched, in_details }: Found, on: 'line' | 'largest' = 'line'): string {
  switch (condition) {
    case 'keyword': {
      const where = on === 'largest'
        ? (in_details ? 'în descrierea liniei celei mai mari' : 'pe linia cea mai mare')
        : (in_details ? 'în descrierea liniei' : 'pe linie')
      const [starts, ends] = [found.startsWith('*'), found.endsWith('*') && found.length > 1]
      const core = found.replace(/^\*+|\*+$/g, '')
      if (!starts && !ends) return `: ${where} scrie „${found}”, unul din cuvintele regulii`
      const what = starts && ends ? 'conține' : starts ? 'se termină cu' : 'începe cu'
      if (!matched) return `: ${where} scrie un cuvânt care ${what} „${core}”`
      return starts && ends
        ? `: ${where} scrie „${matched}”, iar regula caută cuvinte care conțin „${core}”`
        : `: ${where} scrie „${matched}”, care ${what} „${core}”`
    }
    case 'supplier_cui':
      return `: factura vine de la CUI-ul ${found}, iar regula ia toate liniile acestui furnizor`
    case 'seller_code':
      return `: codul articolului, ${found}, este unul din codurile regulii`
    case 'barcode':
      return `: codul de bare, ${found}, este unul din codurile regulii`
    case 'commodity_code':
      return `: codul de clasificare ${found} începe cu ${prefix}`
    default:
      return ''
  }
}
