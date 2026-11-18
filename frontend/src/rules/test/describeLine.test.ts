import { describe, expect, it } from 'vitest'
import type { TrialJev, TrialLineAnswer } from '../../types'
import { describeLine, spentOnJev } from './describeLine'

const jev = (more: Partial<TrialJev> = {}): TrialJev => ({
  choice: '302', confidence: 0.93, threshold: 0.8, refused: false, probabilities: { '302': 0.91, '371': 0.06 },
  cost_usd: 0.00002, duration_ms: 1400, error: null, http_status: 200,
  sent: { question: 'Pe ce cont?', state: { factura: { tip: 'factura', moneda: 'RON' } } }, ...more,
})
const entry = (more: Partial<TrialLineAnswer>): TrialLineAnswer => ({
  line: 2, description: 'Ciment Portland 40 kg', value: '570.00', decided_by: 'nobody', cont: null, account_description: null,
  rule: null, jev: null, why_not: null, reason: '', follows: null, same_as: null, ...more,
})
const asked = { ask: 'rules_then_jev' } as const

describe('what one question to Jev cost', () => {
  it('says the cost and the time, whichever is known', () => {
    expect(spentOnJev(jev())).toBe('A costat < 0,01 $ și a durat 1,4 s.')
    expect(spentOnJev(jev({ cost_usd: null }))).toBe('A durat 1,4 s.')
    expect(spentOnJev(jev({ cost_usd: null, duration_ms: null }))).toBeNull()
  })
})

describe('what the screen says about one line of the trial invoice', () => {
  it('says which rule gave the account and why, and that Jev was not asked', () => {
    const said = describeLine(entry({
      line: 1, decided_by: 'rule', cont: '6022', account_description: 'Combustibil',
      rule: { name: 'combustibil', line: 1, condition: 'keyword', found: 'motorina', prefix: null, client_only: false, also: ['transport'] },
    }), asked)

    expect(said).toMatchObject({ tone: 'done', heading: 'Contul 6022', headingNote: 'Combustibil', chip: { kind: 'rule', text: 'Ales de o regulă' }, jevShown: false })
    expect(said.sentence).toBe('Regula „combustibil”: pe linie scrie „motorina”, unul din cuvintele regulii.')
    expect(said.notes).toEqual([
      'S-ar fi potrivit și regula „transport”, dar „combustibil” este mai sus în listă.',
      'Jev nu a fost întrebat pentru această linie.',
    ])
  })

  it('says Jev gave the account, how sure it was against the level, and offers what it said', () => {
    const said = describeLine(entry({ decided_by: 'jev', cont: '302', account_description: 'Materiale consumabile', jev: jev() }), asked)

    expect(said).toMatchObject({ tone: 'done', heading: 'Contul 302', chip: { kind: 'jev', text: 'Ales de Jev' }, jevShown: true })
    expect(said.sentence).toBe('Nicio regulă nu s-a potrivit. Jev este sigur 93%, iar pragul dumneavoastră este 80%, deci linia primește contul.')
  })

  it('says the rules were skipped when Jev was asked directly', () => {
    const said = describeLine(entry({ decided_by: 'jev', cont: '302', jev: jev() }), { ask: 'jev_only' })

    expect(said.sentence.startsWith('Regulile au fost sărite, cum ați cerut. Jev este sigur 93%')).toBe(true)
  })

  it('says a line that reads like an earlier one shares its answer and its question', () => {
    const said = describeLine(entry({ line: 5, decided_by: 'jev', cont: '302', jev: jev(), same_as: 2 }), asked)

    expect(said.sentence).toBe('La fel ca linia 2: scrie același lucru, deci Jev a fost întrebat o singură dată pentru amândouă.')
    expect(said.jevShown).toBe(false)
  })

  it('gives a line that shares its question the same state as the line Jev was asked about', () => {
    const below = describeLine(entry({ line: 5, why_not: 'below_threshold', jev: jev({ choice: '628', confidence: 0.61 }), same_as: 2 }), asked)
    const failed = describeLine(entry({ line: 5, why_not: 'jev_failed', jev: jev({ choice: null, confidence: null, error: 'HTTP 500', http_status: 500 }), same_as: 2 }), asked)

    expect(below).toMatchObject({ heading: 'De verificat', headingNote: 'Jev propune contul 628', chip: { kind: 'waiting', text: 'Sub prag' }, jevShown: false })
    expect(below.sentence).toBe('La fel ca linia 2: scrie același lucru, deci Jev a fost întrebat o singură dată pentru amândouă.')
    expect(below.notes).toEqual(['Nicio regulă nu s-a potrivit. Jev este sigur doar 61%, sub pragul dumneavoastră de 80%.'])
    expect(failed).toMatchObject({ heading: 'Jev nu a putut fi întrebat.', technical: 'HTTP 500' })
  })

  it('says a line was not sent once OpenRouter failed on an earlier one', () => {
    const said = describeLine(entry({ line: 3, why_not: 'not_asked' }), { ...asked, stoppedAt: 1 })

    expect(said).toMatchObject({ tone: 'attention', heading: 'De verificat', jevShown: false })
    expect(said.sentence).toBe('Nu a mai fost trimisă lui Jev, pentru că întrebarea despre linia 1 nu a reușit.')
  })

  it('does not speak of rules not matching when they were skipped', () => {
    expect(describeLine(entry({ why_not: 'no_key' }), { ask: 'jev_only' }).sentence).toBe('Regulile au fost sărite, iar Jev nu a putut fi întrebat.')
  })

  it('says Jev was not sure enough', () => {
    const said = describeLine(entry({ why_not: 'below_threshold', jev: jev({ choice: '628', confidence: 0.61 }) }), asked)

    expect(said).toMatchObject({ tone: 'attention', heading: 'De verificat', headingNote: 'Jev propune contul 628', chip: { kind: 'waiting', text: 'Sub prag' }, jevShown: true })
    expect(said.sentence).toBe('Nicio regulă nu s-a potrivit. Jev este sigur doar 61%, sub pragul dumneavoastră de 80%.')
  })

  it('tells apart the three ways Jev leaves a line without an account', () => {
    const noneFits = describeLine(entry({ why_not: 'jev_declined', jev: jev({ choice: null, confidence: 0.72, probabilities: { altul: 0.72 } }) }), asked)
    const refused = describeLine(entry({ why_not: 'jev_declined', jev: jev({ choice: null, confidence: null, refused: true, probabilities: {} }) }), asked)
    const unsure = describeLine(entry({ why_not: 'jev_declined', jev: jev({ choice: '628', confidence: null }) }), asked)

    expect(noneFits).toMatchObject({ tone: 'attention', heading: 'De verificat', headingNote: 'niciun cont din listă', jevShown: true })
    expect(noneFits.sentence).toBe('Jev crede că niciun cont din lista dumneavoastră nu se potrivește cu ce s-a cumpărat pe această linie.')
    expect(noneFits.notes).toEqual([
      'Jev alege după descrierea conturilor. Dacă un cont ar trebui să se potrivească, scrieți-i descrierea mai clar sau adăugați contul la „Reguli de clasificare”.',
    ])
    expect(refused).toMatchObject({ headingNote: 'Jev a refuzat', sentence: 'Jev a refuzat să răspundă la întrebarea despre această linie.' })
    expect(refused.notes).toEqual(['Când refuză, Jev nu trimite nimic altceva: niciun cont și nicio cifră despre cât de potrivit i se pare vreunul.'])
    expect(unsure).toMatchObject({
      headingNote: 'Jev propune contul 628',
      sentence: 'Jev a ales contul 628, dar nu a spus cât de sigur este. Fără această cifră, programul nu dă contul singur.',
    })
  })

  it('speaks of the invoice when one account is decided for the whole of it', () => {
    const said = describeLine(entry({ why_not: 'jev_declined', jev: jev({ choice: null, probabilities: { altul: 0.6 } }) }), { ...asked, wholeInvoice: true })

    expect(said.sentence).toBe('Jev crede că niciun cont din lista dumneavoastră nu se potrivește cu ce s-a cumpărat pe această factură.')
  })

  it('says a discount or a line worth nothing takes the account of the largest line', () => {
    const discount = describeLine(entry({ line: 4, value: '-50', decided_by: 'follows', follows: 1, cont: '6022', account_description: 'Combustibil' }), asked)
    const nothing = describeLine(entry({ line: 4, value: '0.00', decided_by: 'follows', follows: 1, cont: '6022' }), asked)
    const waiting = describeLine(entry({ line: 4, value: '-50', decided_by: 'follows', follows: 1 }), asked)

    expect(discount).toMatchObject({ tone: 'done', heading: 'Contul 6022', chip: { kind: 'follows', text: 'Ca linia 1' }, jevShown: false })
    expect(discount.sentence).toBe('Este o reducere, deci primește contul liniei 1, cea mai mare de pe factură.')
    expect(discount.notes).toEqual(['Jev nu a fost întrebat pentru această linie.'])
    expect(nothing.sentence).toBe('Linia are valoarea 0, deci primește contul liniei 1, cea mai mare de pe factură.')
    expect(waiting).toMatchObject({ tone: 'attention', heading: 'De verificat' })
    expect(waiting.notes).toEqual(['Linia 1 nu are încă un cont, deci nici aceasta.'])
  })

  it('says Jev could not answer about the line, and why', () => {
    const refusedKey = describeLine(entry({ why_not: 'jev_failed', jev: jev({ choice: null, confidence: null, error: 'HTTP 401', http_status: 401 }) }), asked)
    const failed = describeLine(entry({ why_not: 'jev_failed', jev: jev({ choice: null, confidence: null, error: 'HTTP 500', http_status: 500 }) }), asked)
    const tooLong = describeLine(entry({ why_not: 'jev_failed', reason: 'This line and the list of accounts do not fit in one request to Jev.' }), asked)
    const noKey = describeLine(entry({ why_not: 'no_key' }), asked)

    expect(refusedKey).toMatchObject({ tone: 'attention', heading: 'Jev nu a putut fi întrebat.', technical: 'HTTP 401', jevShown: false })
    expect(refusedKey.sentence).toBe('OpenRouter a refuzat întrebarea. Verificați cheia OpenRouter și creditul din cont.')
    expect(failed.sentence).toBe('Jev nu a răspuns. Încercați din nou puțin mai târziu.')
    expect(tooLong.sentence).toBe('Linia și lista de conturi nu încap într-o singură întrebare pentru Jev.')
    expect(noKey).toMatchObject({ heading: 'De verificat', sentence: 'Nicio regulă nu s-a potrivit, iar Jev nu a putut fi întrebat.' })
  })
})
