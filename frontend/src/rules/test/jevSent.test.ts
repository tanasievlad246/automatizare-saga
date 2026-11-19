import { describe, expect, it } from 'vitest'
import { jevSent } from './jevSent'

const QUESTION = 'Pe ce cont contabil se înregistrează această linie?'

describe('what was sent to Jev, in words', () => {
  it('says the question, the supplier, the invoice, the line and the accounts', () => {
    const rows = jevSent({
      question: QUESTION,
      state: {
        furnizor: { nume: 'Dedeman SRL', cui: '2816464' },
        factura: { tip: 'factura', moneda: 'RON' },
        linia: { nr: 2, descriere: 'Ciment Portland 40 kg', cantitate: '20', valoare_fara_tva: '570.00', cota_tva: '19.00' },
      },
    }, 5)

    expect(rows).toEqual([
      { label: 'Întrebarea', value: `„${QUESTION}”` },
      { label: 'Furnizorul', value: 'Dedeman SRL, CUI 2816464' },
      { label: 'Factura', value: 'factură, în RON' },
      { label: 'Linia', value: 'Ciment Portland 40 kg · cantitatea 20 · 570,00 fără TVA · TVA 19%' },
      { label: 'Conturile', value: 'cele 5 conturi de la „Reguli de clasificare”, fiecare cu descrierea lui, și „Niciunul din listă”' },
    ])
  })

  it('says the codes and the unit of a line when it has them, and a credit note by its name', () => {
    const rows = jevSent({
      question: QUESTION,
      state: {
        factura: { tip: 'nota de credit', moneda: 'EUR' },
        linia: { nr: 1, descriere: 'Toner', cod_furnizor: 'TN-2420', coduri_clasificare: ['30125100'], um: 'H87', cantitate: '-2', valoare_fara_tva: '-80.00' },
      },
    }, 1)

    expect(rows.find((row) => row.label === 'Factura')?.value).toBe('notă de credit, în EUR')
    expect(rows.find((row) => row.label === 'Linia')?.value).toBe(
      'Toner · cantitatea -2 (H87) · -80,00 fără TVA · codul articolului TN-2420 · cod de clasificare 30125100',
    )
    expect(rows.some((row) => row.label === 'Furnizorul')).toBe(false)
    expect(rows.at(-1)?.value).toBe('contul de la „Reguli de clasificare”, cu descrierea lui, și „Niciunul din listă”')
  })

  it('says the description of a line after its name when it was sent', () => {
    const rows = jevSent({
      question: QUESTION,
      state: {
        factura: { tip: 'factura', moneda: 'RON' },
        linia: { nr: 1, descriere: 'Cartușe toner', detalii: 'Cartuș compatibil HP 85A', cantitate: '6' },
      },
    }, 1)

    expect(rows.find((row) => row.label === 'Linia')?.value).toBe('Cartușe toner · „Cartuș compatibil HP 85A” · cantitatea 6')
  })

  it('says plainly when the supplier was sent without a name or a CUI', () => {
    const supplier = (nume: string | null, cui: string | null) => jevSent({
      question: QUESTION, state: { furnizor: { nume, cui }, factura: { tip: 'factura', moneda: 'RON' }, linia: { nr: 1, descriere: 'Ciment' } },
    }, 2).find((row) => row.label === 'Furnizorul')?.value

    expect(supplier(null, null)).toBe('fără nume, fără CUI')
    expect(supplier('Dedeman SRL', null)).toBe('Dedeman SRL, fără CUI')
  })

  it('lists every line sent for the whole invoice, which one decides, and how many were left out', () => {
    const rows = jevSent({
      question: QUESTION,
      state: {
        factura: { tip: 'factura', moneda: 'RON', total_fara_tva: '1290.00' },
        linia_cu_valoarea_cea_mai_mare: 1,
        linii: [
          { nr: 1, descriere: 'Motorină', valoare_fara_tva: '720.00' },
          { nr: 2, descriere: 'Ciment', valoare_fara_tva: '570.00' },
        ],
        linii_omise: 3,
      },
    }, 2)

    expect(rows.find((row) => row.label === 'Factura')?.value).toBe('factură, în RON, total fără TVA 1.290,00')
    expect(rows.filter((row) => row.label.startsWith('Linia ')).map((row) => [row.label, row.value])).toEqual([
      ['Linia 1', 'Motorină · 720,00 fără TVA (după ea se hotărăște)'],
      ['Linia 2', 'Ciment · 570,00 fără TVA'],
    ])
    expect(rows.find((row) => row.label === 'Lăsate deoparte')?.value).toBe(
      '3 linii mai mici, ca întrebarea să nu fie prea lungă',
    )
  })
})
