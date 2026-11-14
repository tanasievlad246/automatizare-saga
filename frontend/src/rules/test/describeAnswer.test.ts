import { describe, expect, it } from 'vitest'
import { describeAnswer } from './describeAnswer'

const nothing = { rule: null, jev: null, why_not: null, reason: '', suggestion: null, cont: null, account_description: null, deciding_line: null }
const jev = (more: object = {}) => ({
  choice: '302', confidence: 0.93, threshold: 0.8, refused: false, probabilities: { '302': 0.93, '371': 0.27, '628': 0.09 },
  cost_usd: 0.00002, duration_ms: 1400, error: null, http_status: 200, ...more,
})
const answer = (more: object) => ({ ...nothing, decided_by: 'nobody', ...more }) as never

describe('the answer to a trial invoice', () => {
  it('says a rule decided and Jev was not asked', () => {
    const said = describeAnswer(answer({
      decided_by: 'rule', cont: '6022', account_description: 'Combustibil', deciding_line: 'Motorină Euro 5', rule: { name: 'combustibil', line: 1 },
    }), 'rules_then_jev')
    expect(said).toMatchObject({ tone: 'done', title: 'Contul 6022', subtitle: 'Combustibil', label: 'Ales de o regulă' })
    expect(said.sentences).toEqual(['Regula dumneavoastră „combustibil”, pentru rândul „Motorină Euro 5”.', 'Jev nu a fost întrebat, deci nu a costat nimic.'])
  })

  it('says Jev decided, what else it weighed, and what that cost', () => {
    const said = describeAnswer(answer({ decided_by: 'jev', cont: '302', account_description: 'Materiale consumabile', jev: jev() }), 'rules_then_jev')
    expect(said).toMatchObject({ tone: 'done', title: 'Contul 302', subtitle: 'Materiale consumabile', label: 'Ales de Jev' })
    expect(said.sentences).toEqual([
      'Nicio regulă nu s-a potrivit, așa că a fost întrebat Jev.',
      'Cât de sigur este: 93%. Pragul dumneavoastră este 80%, deci o factură adevărată ar fi primit contul fără să vă mai întrebe.',
      'S-a gândit și la: 371 (27%), 628 (9%).',
      'A costat 0,00002 $ și a durat 1,4 s.',
    ])
  })

  it('says the rules were skipped when Jev was asked directly, and leaves out the other accounts when there are none', () => {
    const said = describeAnswer(answer({ decided_by: 'jev', cont: '302', jev: jev({ probabilities: { '302': 0.93 } }) }), 'jev_only')
    expect(said.sentences[0]).toBe('Regulile au fost sărite.')
    expect(said.sentences.some((sentence) => sentence.startsWith('S-a gândit'))).toBe(false)
  })

  it('says Jev was not sure enough', () => {
    const said = describeAnswer(answer({ why_not: 'below_threshold', jev: jev({ choice: '628', confidence: 0.61 }) }), 'rules_then_jev')
    expect(said).toMatchObject({ tone: 'attention', title: 'De verificat', subtitle: 'Jev propune contul 628', label: null })
    expect(said.sentences).toEqual([
      'Jev este sigur doar 61%, sub pragul dumneavoastră de 80%.',
      'O factură adevărată ar aștepta la „De verificat” până îi alegeți dumneavoastră contul.',
    ])
  })

  it('says Jev declined', () => {
    const said = describeAnswer(answer({ why_not: 'jev_declined', jev: jev({ choice: null, confidence: null }) }), 'rules_then_jev')
    expect(said).toMatchObject({ tone: 'attention', title: 'De verificat', subtitle: 'Jev nu a ales niciun cont pentru această factură.' })
  })

  it('says why Jev could not be asked', () => {
    const asked = (why_not: string) => describeAnswer(answer({ why_not }), 'rules_then_jev')
    expect(asked('no_lines')).toMatchObject({ tone: 'attention', title: 'Jev nu a putut fi întrebat.', sentences: ['Factura de probă nu are niciun rând.'], technical: null })
    expect(asked('no_key').sentences).toEqual([
      'Lipsește cheia OpenRouter. O scrieți la „Chei și parole”.',
      'Regulile se pot încerca și fără cheie: dacă o regulă se potrivește, răspunsul vine de la ea.',
    ])
    expect(asked('no_accounts').sentences).toEqual(['Nu există niciun cont din care Jev să aleagă. Le adăugați la „Reguli de clasificare”.'])
  })

  it('says Jev did not answer, with the program\'s words under the technical details', () => {
    const said = describeAnswer(answer({ why_not: 'jev_failed', jev: jev({ choice: null, error: 'HTTP 502 from OpenRouter', http_status: 502 }) }), 'rules_then_jev')
    expect(said.sentences).toEqual(['Jev nu a răspuns. Încercați din nou puțin mai târziu.'])
    expect(said.technical).toBe('HTTP 502 from OpenRouter')
    const unreached = describeAnswer(answer({ why_not: 'jev_failed', jev: jev({ choice: null, error: 'connection reset', http_status: null }) }), 'rules_then_jev')
    expect(unreached.sentences).toEqual(['Jev nu a răspuns. Încercați din nou puțin mai târziu.'])
    // A request too large to send has no answer from Jev at all; the program's own line is shown.
    expect(describeAnswer(answer({ why_not: 'jev_failed', reason: 'Does not fit in one request.' }), 'rules_then_jev').technical).toBe('Does not fit in one request.')
  })

  it.each([401, 402, 403])('says a refusal with HTTP %i is the key or the credit, which waiting does not mend', (status) => {
    const said = describeAnswer(answer({ why_not: 'jev_failed', jev: jev({ choice: null, error: `OpenRouter refused (HTTP ${status})`, http_status: status }) }), 'rules_then_jev')
    expect(said).toMatchObject({ title: 'Jev nu a putut fi întrebat.', technical: `OpenRouter refused (HTTP ${status})` })
    expect(said.sentences).toEqual(['OpenRouter a refuzat întrebarea. Verificați cheia OpenRouter și creditul din cont.'])
  })
})
