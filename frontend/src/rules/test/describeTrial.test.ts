import { describe, expect, it } from 'vitest'
import type { RuleTestResult, TrialJev, TrialLineAnswer } from '../../types'
import { describeTrial } from './describeTrial'

const jev = (more: Partial<TrialJev> = {}): TrialJev => ({
  choice: '302', confidence: 0.93, threshold: 0.8, refused: false, probabilities: { '302': 0.93 },
  cost_usd: 0.00002, duration_ms: 1400, error: null, http_status: 200,
  sent: { question: '?', state: { factura: { tip: 'factura', moneda: 'RON' } } }, ...more,
})
const line = (number: number, more: Partial<TrialLineAnswer>): TrialLineAnswer => ({
  line: number, description: `Linia ${number}`, value: '100.00', decided_by: 'nobody', cont: null, account_description: null,
  rule: null, jev: null, why_not: null, reason: '', follows: null, same_as: null, ...more,
})
const result = (more: Partial<RuleTestResult>): RuleTestResult => ({
  per_line: true, lines: [], decided_by: 'nobody', cont: null, account_description: null, deciding_line: null, rule: null, jev: null,
  why_not: null, reason: '', accounts: {}, jev_calls: 0, cost_usd: null, suggestion: null, ...more,
})
const RULE = { name: 'combustibil', line: 1, condition: 'keyword' as const, found: 'motorina', prefix: null, client_only: false, also: [] }

describe('the answer to a trial invoice decided line by line', () => {
  it('says which lines have an account and which wait, and what asking Jev cost', () => {
    const said = describeTrial(result({
      waiting: 1, jev_calls: 2, cost_usd: 0.00004,
      lines: [
        line(1, { decided_by: 'rule', cont: '6022', rule: RULE }),
        line(2, { decided_by: 'jev', cont: '302', jev: jev() }),
        line(3, { why_not: 'below_threshold', jev: jev({ choice: '628', confidence: 0.61 }) }),
        line(4, { decided_by: 'follows', follows: 1, cont: '6022' }),
      ],
    }), 4, 'rules_then_jev')

    expect(said).toMatchObject({ tone: 'attention', title: 'De verificat', subtitle: '3 linii au cont, linia 3 așteaptă', failed: false })
    expect(said.sentences).toEqual([
      'O factură adevărată ar aștepta la „De verificat” până alegeți contul liniei 3. Celelalte linii își păstrează contul.',
      'Jev a fost întrebat de 2 ori, câte o dată pentru liniile 2 și 3. A costat < 0,01 $ în total.',
    ])
  })

  it('says every line has an account, on which accounts', () => {
    const said = describeTrial(result({
      waiting: 0,
      lines: [line(1, { decided_by: 'rule', cont: '6022', rule: RULE }), line(2, { decided_by: 'rule', cont: '302', rule: RULE }), line(3, { decided_by: 'follows', follows: 1, cont: '6022' })],
    }), 3, 'rules_then_jev')

    expect(said).toMatchObject({ tone: 'done', title: 'Toate liniile au cont', subtitle: 'Conturile 6022 și 302' })
    expect(said.sentences).toEqual([
      'O factură adevărată ar primi aceste conturi fără să vă mai întrebe.',
      'Jev nu a fost întrebat, deci nu a costat nimic.',
    ])
  })

  it('names the lines to choose for, leaving out a discount that only waits for the largest line', () => {
    const said = describeTrial(result({
      waiting: 3, jev_calls: 1, cost_usd: 0.00002,
      lines: [
        line(1, { why_not: 'jev_declined', jev: jev({ choice: null }) }),
        line(2, { why_not: 'jev_declined', jev: jev({ choice: null }), same_as: 1 }),
        line(3, { decided_by: 'follows', follows: 1 }),
      ],
    }), 3, 'rules_then_jev')

    expect(said.subtitle).toBe('Nicio linie nu are cont')
    expect(said.sentences).toEqual([
      'O factură adevărată ar aștepta la „De verificat” până alegeți contul liniilor 1 și 2.',
      'Jev a fost întrebat o dată, pentru linia 1. A costat < 0,01 $.',
    ])
  })

  it('says once why Jev could not be asked, not on every line', () => {
    const said = describeTrial(result({
      waiting: 1,
      lines: [line(1, { decided_by: 'rule', cont: '6022', rule: RULE }), line(2, { why_not: 'no_key' })],
    }), 2, 'rules_then_jev')

    expect(said.subtitle).toBe('o linie are cont, linia 2 așteaptă')
    expect(said.sentences).toContain('Lipsește cheia OpenRouter. O scrieți la „Chei și parole”.')
  })
})

describe('the answer to a trial invoice when Jev cannot be reached', () => {
  it('says Jev could not be asked, why, and that the lines left were not sent', () => {
    const said = describeTrial(result({
      waiting: 3, jev_calls: 1, cost_usd: 0, jev_stopped: { line: 1, http_status: 401, error: 'HTTP 401: No auth credentials found' },
      lines: [
        line(1, { why_not: 'jev_failed', jev: jev({ choice: null, confidence: null, error: 'HTTP 401', http_status: 401, cost_usd: null }) }),
        line(2, { why_not: 'not_asked' }), line(3, { why_not: 'not_asked' }),
      ],
    }), 3, 'rules_then_jev')

    expect(said).toMatchObject({ failed: true, title: 'Jev nu a putut fi întrebat.', subtitle: 'Nicio linie nu are cont', technical: 'HTTP 401: No auth credentials found' })
    expect(said.sentences).toEqual([
      'OpenRouter a refuzat întrebarea. Verificați cheia OpenRouter și creditul din cont.',
      'Întrebarea despre linia 1 nu a reușit, așa că celelalte linii nu au mai fost trimise. O factură adevărată ar rămâne în așteptare, iar Jev ar fi întrebat din nou la următoarea descărcare.',
      'Jev a fost întrebat o dată, pentru linia 1. Nu a costat nimic.',
    ])
  })
})

describe('what the answer says beyond the first lines', () => {
  it('says "de" before twenty or more questions, as Romanian does', () => {
    const lines = Array.from({ length: 20 }, (_, index) => line(index + 1, { decided_by: 'jev', cont: '302', jev: jev() }))

    expect(describeTrial(result({ waiting: 0, jev_calls: 20, cost_usd: 0.0004, lines }), 20, 'rules_then_jev').sentences[1].startsWith('Jev a fost întrebat de 20 de ori, câte o dată pentru liniile 1, 2,')).toBe(true)
  })

  it('does not promise the accounts of a real invoice when the rules were skipped', () => {
    const lines = [line(1, { decided_by: 'jev', cont: '302', jev: jev() }), line(2, { decided_by: 'jev', cont: '302', jev: jev() })]

    expect(describeTrial(result({ waiting: 0, jev_calls: 2, cost_usd: 0.00004, lines }), 2, 'jev_only').sentences[0]).toBe(
      'Regulile au fost sărite. O factură adevărată ar trece întâi prin reguli, deci ar putea primi alt cont.',
    )
    expect(describeTrial(result({ per_line: false, decided_by: 'jev', cont: '302', jev: jev(), jev_calls: 1 }), 1, 'jev_only').sentences[0]).toBe(
      'Regulile au fost sărite. O factură adevărată ar trece întâi prin reguli, deci ar putea primi alt cont.',
    )
  })
})

describe('the answer to a trial invoice with one account', () => {
  it('says the account and, for several lines, the line it was decided by', () => {
    const said = describeTrial(result({
      per_line: false, decided_by: 'rule', cont: '6022', account_description: 'Combustibil', deciding_line: 'Motorină Euro 5', rule: RULE,
      lines: [line(1, { decided_by: 'rule', cont: '6022', rule: RULE })],
    }), 3, 'rules_then_jev')

    expect(said).toMatchObject({ tone: 'done', title: 'Contul 6022', subtitle: 'Combustibil' })
    expect(said.sentences).toEqual([
      'Clientul are un singur cont pe factură: s-a hotărât după linia „Motorină Euro 5”, cea cu valoarea cea mai mare.',
      'Jev nu a fost întrebat, deci nu a costat nimic.',
    ])
    expect(describeTrial(result({ per_line: false, decided_by: 'rule', cont: '6022', rule: RULE }), 1, 'rules_then_jev').sentences).toEqual([
      'Jev nu a fost întrebat, deci nu a costat nimic.',
    ])
  })

  it('says what Jev cost and how long it took', () => {
    const said = describeTrial(result({ per_line: false, decided_by: 'jev', cont: '302', jev: jev(), jev_calls: 1, cost_usd: 0.00002 }), 1, 'rules_then_jev')

    expect(said.sentences).toEqual([
      'O factură adevărată ar primi contul fără să vă mai întrebe.',
      'A costat < 0,01 $ și a durat 1,4 s.',
    ])
  })

  it('tells apart why the invoice waits', () => {
    const waits = (more: Partial<RuleTestResult>) => describeTrial(result({ per_line: false, jev_calls: 1, ...more }), 1, 'rules_then_jev')

    expect(waits({ why_not: 'below_threshold', jev: jev({ choice: '628', confidence: 0.61 }) })).toMatchObject({ tone: 'attention', title: 'De verificat', subtitle: 'Jev propune contul 628' })
    expect(waits({ why_not: 'jev_declined', jev: jev({ choice: null }) }).subtitle).toBe('Jev nu a ales niciun cont din listă')
    expect(waits({ why_not: 'jev_declined', jev: jev({ choice: null, confidence: null, refused: true }) }).subtitle).toBe('Jev a refuzat să răspundă')
    expect(waits({ why_not: 'jev_declined', jev: jev({ choice: '628', confidence: null }) }).subtitle).toBe('Jev propune contul 628, fără să spună cât de sigur este')
    expect(waits({ why_not: 'below_threshold', jev: jev({ choice: '628', confidence: 0.61 }) }).sentences[0]).toBe(
      'O factură adevărată ar aștepta la „De verificat” până îi alegeți dumneavoastră contul.',
    )
  })

  it('says why Jev could not be asked', () => {
    const asked = (more: Partial<RuleTestResult>) => describeTrial(result({ per_line: false, ...more }), 1, 'rules_then_jev')

    expect(asked({ why_not: 'no_lines' })).toMatchObject({ failed: true, title: 'Jev nu a putut fi întrebat.', sentences: ['Factura de probă nu are niciun rând.'], technical: null })
    expect(asked({ why_not: 'no_key' }).sentences).toEqual([
      'Lipsește cheia OpenRouter. O scrieți la „Chei și parole”.',
      'Regulile se pot încerca și fără cheie: dacă o regulă se potrivește, răspunsul vine de la ea.',
    ])
    expect(asked({ why_not: 'no_accounts' }).sentences).toEqual(['Nu există niciun cont din care Jev să aleagă. Le adăugați la „Reguli de clasificare”.'])
    expect(asked({ why_not: 'jev_failed', jev: jev({ choice: null, error: 'HTTP 402', http_status: 402 }), jev_calls: 1 })).toMatchObject({
      sentences: ['OpenRouter a refuzat întrebarea. Verificați cheia OpenRouter și creditul din cont.'], technical: 'HTTP 402',
    })
    expect(asked({ why_not: 'jev_failed', reason: 'The invoice and the list of accounts do not fit in one request to Jev.' })).toMatchObject({
      sentences: ['Factura și lista de conturi nu încap într-o singură întrebare pentru Jev.'],
    })
  })
})
