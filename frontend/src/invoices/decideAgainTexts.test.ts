import { describe, expect, it } from 'vitest'
import {
  DECIDE_AGAIN, LINE_AGAIN, NO_JEV, SPLIT, decideAgainChoices, decideAgainPoints, followersNote, importedSteps, splitNote,
} from './decideAgainTexts'

describe('"Hotărăște din nou…" for the whole invoice', () => {
  it('offers the rules then Jev, or Jev alone, said for an invoice on lines or with one account', () => {
    expect(decideAgainChoices(true).map((choice) => [choice.value, choice.label])).toEqual([
      ['rules_then_jev', 'Cu regulile, apoi Jev'], ['jev_only', 'Doar cu Jev'],
    ])
    expect(decideAgainChoices(true)[1].help).toBe(
      'Regulile sunt sărite: Jev este întrebat despre fiecare linie, chiar și unde o regulă se potrivește. Așa vedeți ce ar alege Jev singur.',
    )
    expect(decideAgainChoices(false)[1].help).toBe(
      'Regulile sunt sărite: Jev este întrebat despre factură, chiar dacă o regulă se potrivește. Așa vedeți ce ar alege Jev singur.',
    )
  })

  it('says the invoice is decided from the start and keeps its shape', () => {
    expect(decideAgainPoints({ perLine: true, lines: 3 })).toEqual([
      'Factura se hotărăște de la început. Contul de acum și conturile pe care le-ați ales pe linii se hotărăsc și ele din nou.',
      'Factura este pe linii și rămâne pe linii: fiecare linie primește contul ei.',
      'Ce nu poate hotărî nimeni vine la verificat. Fiecare întrebare pentru Jev costă puțin.',
    ])
    expect(decideAgainPoints({ perLine: false, lines: 3 })[1]).toBe(
      'Factura are un singur cont și rămâne așa: contul se alege după linia cea mai mare. Ca liniile să primească conturi diferite, folosiți întâi „Împarte pe linii”.',
    )
    expect(decideAgainPoints({ perLine: false, lines: 1 })).toEqual([
      'Factura se hotărăște de la început. Contul de acum se hotărăște și el din nou.',
      'Ce nu poate hotărî nimeni vine la verificat. Fiecare întrebare pentru Jev costă puțin.',
    ])
  })

  it('has one main button and says why Jev cannot be asked without a key', () => {
    expect([DECIDE_AGAIN.title, DECIDE_AGAIN.button, DECIDE_AGAIN.busy]).toEqual([
      'Hotărăște din nou contul facturii', 'Hotărăște din nou', 'Se hotărăște…',
    ])
    expect(NO_JEV).toBe('Jev nu este pornit. Puneți cheia OpenRouter la „Chei și parole”.')
  })
})

describe('one line decided again', () => {
  it('offers the two ways and says what they cost', () => {
    expect([LINE_AGAIN.heading, LINE_AGAIN.rules, LINE_AGAIN.jev]).toEqual([
      'Sau hotărăște din nou această linie', 'Cu regulile, apoi Jev', 'Doar cu Jev',
    ])
    expect(LINE_AGAIN.note).toBe('„Cu regulile, apoi Jev” face ce face o descărcare. „Doar cu Jev” sare peste reguli. Fiecare întrebare pentru Jev costă puțin.')
    expect(LINE_AGAIN.done(3)).toBe('Linia 3 a fost hotărâtă din nou. Ce s-a ales se vede și la „Cum s-a ales contul”.')
  })

  it('says, for the largest line, which lines move with it', () => {
    expect(followersNote([])).toBeNull()
    expect(followersNote([4])).toBe('Este linia cea mai mare. Linia 4 ia contul ei, așa că se schimbă odată cu ea.')
    expect(followersNote([2, 4, 5])).toBe('Este linia cea mai mare. Liniile 2, 4 și 5 iau contul ei, așa că se schimbă odată cu ea.')
  })
})

describe('"Împarte pe linii"', () => {
  it('says that every line starts with the account, then each is changed or decided again', () => {
    expect(splitNote(2, '302')).toBe(
      'Ambele linii sunt pe contul 302. Ca să le dați conturi diferite, împărțiți factura pe linii: fiecare pornește cu 302, apoi o schimbați sau o hotărâți din nou.',
    )
    expect(splitNote(24, '302')).toMatch(/^Toate cele 24 de linii sunt pe contul 302\./)
    expect([SPLIT.button, SPLIT.done]).toEqual([
      'Împarte pe linii', 'Factura este acum pe linii. Alegeți sau hotărâți din nou contul fiecărei linii, cu „Schimbă”.',
    ])
  })
})

describe('an invoice imported in SAGA', () => {
  it('says, in steps, how its account is changed', () => {
    expect(importedSteps(false)).toEqual({
      intro: 'Factura este deja în SAGA, cu acest cont. Dacă trebuie schimbat:',
      steps: [
        'ștergeți factura din SAGA;', 'scoateți bifa „Am importat factura în SAGA”, mai jos;', 'alegeți contul nou;',
        'importați factura din nou în SAGA.',
      ],
    })
    expect(importedSteps(true).intro).toBe('Factura este deja în SAGA, cu aceste conturi. Dacă trebuie schimbate:')
    expect(importedSteps(true).steps[2]).toBe('alegeți conturile noi;')
  })
})
