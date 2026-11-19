import { describe, expect, it } from 'vitest'
import type { Decision } from '../../types'
import { EMPTY_HISTORY, beforeText, decisionSentence, moments, rowLabel, showAllLabel, sourceLabel } from './decisionTexts'

const decision = (more: Omit<Partial<Decision>, 'said'> & { said?: Partial<Decision['said']> }): Decision => ({
  id: 1, at: '2026-11-19T10:37:00+02:00', source: 'download', line: 1, cont: '302', method: 'rules', reason: '',
  ...more,
  said: {
    rule: null, match: null, suggested_cont: null, confidence: null, confidence_threshold: null, probabilities: null,
    jev_only: false, before: null, ...more.said,
  },
})

describe('when and how the account changed', () => {
  it('names each way an account changes', () => {
    expect(sourceLabel('download', false)).toBe('La descărcare')
    expect(sourceLabel('again', false)).toBe('Clasificată din nou')
    expect(sourceLabel('redecide', false)).toBe('Hotărâtă din nou: regulile, apoi Jev')
    expect(sourceLabel('redecide', true)).toBe('Hotărâtă din nou: doar Jev')
    expect(sourceLabel('person', false)).toBe('Ales de dumneavoastră')
    expect(sourceLabel('split', false)).toBe('Împărțită pe linii de dumneavoastră')
  })

  it('says when there is nothing yet', () => {
    expect(EMPTY_HISTORY).toBe(
      'Încă nu este nimic aici. Istoricul se ține de la versiunea 0.14.0: contul ales înainte se vede în cartonaș, dar nu și cum s-a ajuns la el.',
    )
  })
})

describe('why a line got its account', () => {
  it('names the rule and the words it found, on the line or on the largest line of the invoice', () => {
    const match = { condition: 'keyword' as const, found: '*cartus*', prefix: null, matched: 'cartuse', in_details: true }
    expect(decisionSentence(decision({ said: { rule: 'consumabile', match } }))).toBe(
      'regula „consumabile”: în descrierea liniei scrie „cartuse”, iar regula caută cuvinte care conțin „cartus”',
    )
    expect(decisionSentence(decision({ line: null, said: { rule: 'consumabile', match: { ...match, in_details: false } } }))).toBe(
      'regula „consumabile”: pe linia cea mai mare scrie „cartuse”, iar regula caută cuvinte care conțin „cartus”',
    )
    expect(decisionSentence(decision({}))).toBe('după o regulă a dumneavoastră')
  })

  it('says how sure Jev was against the level, and who else chose', () => {
    expect(decisionSentence(decision({ method: 'jev', said: { confidence: 0.93, confidence_threshold: 0.8 } }))).toBe(
      'ales de Jev, sigur 93% (pragul este 80%)',
    )
    expect(decisionSentence(decision({ method: 'jev_accepted', said: { confidence: 0.58 } }))).toBe(
      'propus de Jev (sigur 58%), acceptat de dumneavoastră',
    )
    expect(decisionSentence(decision({ method: 'human' }))).toBe('ales de dumneavoastră')
    expect(decisionSentence(decision({ method: 'follows' }))).toBe('ca linia cea mai mare')
    expect(decisionSentence(decision({ method: 'invoice' }))).toBe('contul facturii, păstrat la împărțire')
  })

  it('says why a line waits: what Jev proposed, or why nobody could choose', () => {
    expect(decisionSentence(decision({ cont: null, method: null, said: { suggested_cont: '302', confidence: 0.41, confidence_threshold: 0.8 } })))
      .toBe('Jev propune 302, sigur doar 41% (pragul este 80%)')
    expect(decisionSentence(decision({ cont: null, method: null, reason: 'Jev found that none of the accounts fits.' })))
      .toBe('Jev nu a găsit un cont potrivit')
    expect(decisionSentence(decision({ cont: null, method: 'follows' }))).toBe('primește contul liniei celei mai mari, după ce îl alegeți')
    expect(decisionSentence(decision({ cont: null, method: null, reason: 'Something new.' }))).toBe('nimeni nu a putut alege contul')
  })

  it('says what the line had before, when it had something', () => {
    expect(beforeText(decision({}))).toBeNull()
    expect(beforeText(decision({ said: { before: { cont: null, method: null, rule: null } } }))).toBe('înainte: de verificat')
    expect(beforeText(decision({ said: { before: { cont: '302', method: 'rules', rule: 'consumabile' } } }))).toBe(
      'înainte: 302, după regula „consumabile”',
    )
    expect(beforeText(decision({ said: { before: { cont: '302', method: 'invoice', rule: null } } }))).toBe('înainte: 302, contul facturii')
    expect(beforeText(decision({ said: { before: { cont: '302', method: 'jev', rule: null } } }))).toBe('înainte: 302, ales de Jev')
  })
})

describe('the moments of the history', () => {
  it('puts the rows of one change together, the newest change first, its lines in order', () => {
    const rows = [
      decision({ id: 5, at: '2026-11-19T14:02:00+02:00', source: 'person', line: 3, cont: '623', method: 'human' }),
      decision({ id: 4, at: '2026-11-19T10:37:00+02:00', line: 2, method: 'jev', said: { confidence: 0.9, confidence_threshold: 0.8 } }),
      decision({ id: 3, at: '2026-11-19T10:37:00+02:00', line: 1, said: { rule: 'consumabile' } }),
    ]

    const found = moments(rows)

    expect(found.map((moment) => moment.label)).toEqual(['Ales de dumneavoastră', 'La descărcare'])
    expect(found[1].rows.map((row) => row.lines)).toEqual([[1], [2]])
  })

  it('puts the lines that got the same thing in one row', () => {
    const rows = [2, 3, 4].map((line) => decision({ id: line, source: 'split', line, method: 'invoice' }))

    const [moment] = moments(rows)

    expect(moment.rows).toHaveLength(1)
    expect(moment.rows[0]).toMatchObject({ lines: [2, 3, 4], cont: '302', text: 'contul facturii, păstrat la împărțire' })
    expect(moment.lineCount).toBe(3)
  })

  it('keeps Jev\'s likelihood of each account with its row', () => {
    const asked = decision({ method: 'jev', said: { confidence: 0.9, probabilities: { 302: 0.9, 628: 0.1 } } })

    expect(moments([asked])[0].rows[0].odds).toEqual({ probabilities: { 302: 0.9, 628: 0.1 }, choice: '302' })
    expect(moments([decision({})])[0].rows[0].odds).toBeNull()
  })

  it('names the rows by their lines, and the whole invoice as such', () => {
    expect(rowLabel(null, {})).toBe('Factura')
    expect(rowLabel([3], { 3: 'Cafea boabe 1 kg' })).toBe('Linia 3 · Cafea boabe 1 kg')
    expect(rowLabel([2, 3], {})).toBe('Liniile 2 și 3')
    expect(rowLabel([2, 3, 5], {})).toBe('Liniile 2, 3 și 5')
  })

  it('folds a long moment after 6 rows, saying how many lines it holds', () => {
    expect(showAllLabel(7)).toBe('Arată toate cele 7 linii')
    expect(showAllLabel(24)).toBe('Arată toate cele 24 de linii')
  })
})
