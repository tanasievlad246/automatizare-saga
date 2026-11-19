import { countOf, formatAmount, formatNumber } from '../../format'
import type { JevLine, TrialJev } from '../../types'

export type SentRow = { label: string; value: string }

const KINDS: Record<string, string> = { factura: 'factură', 'nota de credit': 'notă de credit' }

/**
 * Everything that left the program for Jev, in words: the question, the supplier, the
 * invoice and its line (or lines), and the accounts it chose from. Nothing else is sent.
 */
export function jevSent(sent: TrialJev['sent'], accountCount: number): SentRow[] {
  const { state } = sent
  const rows: SentRow[] = [{ label: 'Întrebarea', value: `„${sent.question}”` }]
  if (state.furnizor) {
    const { nume, cui } = state.furnizor
    rows.push({ label: 'Furnizorul', value: `${nume || 'fără nume'}, ${cui ? `CUI ${cui}` : 'fără CUI'}` })
  }
  const total = state.factura.total_fara_tva ? `, total fără TVA ${formatAmount(state.factura.total_fara_tva)}` : ''
  rows.push({ label: 'Factura', value: `${KINDS[state.factura.tip] ?? state.factura.tip}, în ${state.factura.moneda}${total}` })
  if (state.linia) rows.push({ label: 'Linia', value: lineInWords(state.linia) })
  for (const line of state.linii ?? []) {
    const deciding = line.nr === state.linia_cu_valoarea_cea_mai_mare ? ' (după ea se hotărăște)' : ''
    rows.push({ label: `Linia ${line.nr}`, value: `${lineInWords(line)}${deciding}` })
  }
  if (state.linii_omise) {
    rows.push({ label: 'Lăsate deoparte', value: `${countOf(state.linii_omise, 'o linie mai mică', 'linii mai mici')}, ca întrebarea să nu fie prea lungă` })
  }
  rows.push({
    label: 'Conturile',
    value: accountCount === 1
      ? 'contul de la „Reguli de clasificare”, cu descrierea lui, și „Niciunul din listă”'
      : `cele ${countOf(accountCount, '', 'conturi')} de la „Reguli de clasificare”, fiecare cu descrierea lui, și „Niciunul din listă”`,
  })
  return rows
}

/** "Ciment Portland 40 kg · „sac 40 kg, gri” · cantitatea 20 · 570,00 fără TVA · TVA 19%". */
function lineInWords(line: JevLine): string {
  const codes = line.coduri_clasificare ?? []
  return [
    line.descriere,
    line.detalii && `„${line.detalii}”`,
    line.cantitate && `cantitatea ${formatNumber(line.cantitate)}${line.um ? ` (${line.um})` : ''}`,
    line.valoare_fara_tva && `${formatAmount(line.valoare_fara_tva)} fără TVA`,
    line.cota_tva && `TVA ${formatNumber(line.cota_tva)}%`,
    line.cod_furnizor && `codul articolului ${line.cod_furnizor}`,
    codes.length > 0 && `${codes.length === 1 ? 'cod' : 'coduri'} de clasificare ${codes.join(', ')}`,
  ].filter(Boolean).join(' · ')
}
