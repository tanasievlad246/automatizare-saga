import type { TrialRule } from '../../types'

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

function because({ condition, found, prefix }: TrialRule): string {
  switch (condition) {
    case 'keyword':
      return found?.endsWith('*')
        ? `: pe linie scrie un cuvânt care începe cu „${found.slice(0, -1)}”`
        : `: pe linie scrie „${found}”, unul din cuvintele regulii`
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
