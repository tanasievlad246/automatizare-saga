import { describe, expect, it } from 'vitest'
import type { Invoice, LineAccount } from '../types'
import { accountsUsed, largestLine, linesLeft, linesLeftNote, listAccount, whoChoseLine } from './lineAccounts'

const entry = (over: Partial<LineAccount>): LineAccount => ({
  line: 1, cont: null, method: null, rule: null, reason: '',
  suggested_cont: null, confidence: null, confidence_threshold: null, probabilities: null, asked: false, ...over,
})
const invoice = (over: Partial<Invoice>) => ({ cont: null, line_accounts: null, ...over }) as Invoice

describe('who chose the account of a line', () => {
  it('names the rule, Jev with how sure it was, the person, or the largest line', () => {
    expect(whoChoseLine(entry({ cont: '605', method: 'rules', rule: 'apă' }))).toBe('după regula „apă”')
    expect(whoChoseLine(entry({ cont: '605', method: 'rules' }))).toBe('după o regulă a dumneavoastră')
    expect(whoChoseLine(entry({ cont: '605', method: 'jev', confidence: 0.93 }))).toBe('ales de Jev, sigur 93%')
    expect(whoChoseLine(entry({ cont: '628', method: 'jev_accepted' }))).toBe('propus de Jev, acceptat de dumneavoastră')
    expect(whoChoseLine(entry({ cont: '628', method: 'human' }))).toBe('ales de dumneavoastră')
    expect(whoChoseLine(entry({ cont: '605', method: 'follows' }))).toBe('ca linia cea mai mare')
    expect(whoChoseLine(entry({ cont: '302', method: 'invoice' }))).toBe('contul facturii, păstrat la împărțire')
  })

  it('says what Jev proposed for a line that waits', () => {
    expect(whoChoseLine(entry({ suggested_cont: '6581', confidence: 0.55 }))).toBe('Jev propune 6581, sigur doar 55%')
    expect(whoChoseLine(entry({ suggested_cont: '6581' }))).toBe('Jev propune 6581, fără să spună cât de sigur este')
  })

  it('says in plain words why a line without a proposal waits', () => {
    expect(whoChoseLine(entry({ reason: 'The same invoice (supplier, number and date) is already saved as message 3001.' })))
      .toBe('factura pare trimisă de două ori')
    expect(whoChoseLine(entry({ reason: 'No rule matched this line, and OpenRouter is not set up ([openrouter] api_key in config.toml).' })))
      .toBe('nicio regulă nu se potrivește, iar Jev nu este pornit')
    expect(whoChoseLine(entry({ reason: 'No rule matched this line, and there are no accounts for Jev to choose from.' })))
      .toBe('nicio regulă nu se potrivește, iar Jev nu are conturi din care să aleagă')
    expect(whoChoseLine(entry({ reason: 'Jev declined to answer.' }))).toBe('Jev nu a vrut să răspundă')
    expect(whoChoseLine(entry({ reason: 'Jev found that none of the accounts fits.' }))).toBe('Jev nu a găsit un cont potrivit')
    expect(whoChoseLine(entry({ reason: 'Jev could not decide this line: HTTP 400' }))).toBe('Jev nu a dat un răspuns folosibil')
    expect(whoChoseLine(entry({ reason: 'This line and the list of accounts do not fit in one request to Jev.' })))
      .toBe('linia și lista de conturi nu încap într-o întrebare pentru Jev')
    expect(whoChoseLine(entry({ reason: 'Waiting: OpenRouter failed before Jev was asked about this line.' })))
      .toBe('Jev nu a putut fi întrebat încă; programul încearcă din nou la următoarea descărcare')
    expect(whoChoseLine(entry({ reason: 'Something new' }))).toBe('alegeți contul acestei linii')
    expect(whoChoseLine(entry({ method: 'follows' }))).toBe('primește contul liniei celei mai mari, după ce îl alegeți')
  })
})

describe('the accounts of an invoice decided line by line', () => {
  const lines = [
    entry({ line: 1, cont: '605' }), entry({ line: 2, cont: '6581' }), entry({ line: 3, cont: '605' }), entry({ line: 4 }),
  ]

  it('are listed with how many lines each has, the most used first', () => {
    expect(accountsUsed(lines)).toEqual([{ cont: '605', lines: 2 }, { cont: '6581', lines: 1 }])
    expect(accountsUsed([])).toEqual([])
  })

  it('count the lines still without an account', () => {
    expect(linesLeft(lines)).toBe(1)
    expect(linesLeft(lines.slice(0, 3))).toBe(0)
  })

  it('do not count a line that only waits for the largest one: it needs no choice of its own', () => {
    expect(linesLeft([entry({ line: 1 }), entry({ line: 2, method: 'follows' })])).toBe(1)
  })

  it('say what waiting lines hold back', () => {
    expect(linesLeftNote(1)).toBe('O linie nu are încă un cont. Factura intră în fișierul pentru SAGA după ce îl alegeți.')
    expect(linesLeftNote(3)).toBe('3 linii nu au încă un cont. Factura intră în fișierul pentru SAGA după ce le alegeți.')
  })
})

describe('the account column of a list', () => {
  it('shows the one account of an invoice decided whole, or none', () => {
    expect(listAccount(invoice({ cont: '6022' }))).toEqual({ main: '6022', more: null })
    expect(listAccount(invoice({}))).toEqual({ main: null, more: null })
  })

  it('shows the invoice account and how many others its lines have', () => {
    const lines = [entry({ line: 1, cont: '704' }), entry({ line: 2, cont: '707' }), entry({ line: 3, cont: '704' })]

    expect(listAccount(invoice({ cont: '704', line_accounts: lines }))).toEqual({ main: '704', more: '+1' })
    expect(listAccount(invoice({ cont: '704', line_accounts: lines.slice(0, 1) }))).toEqual({ main: '704', more: null })
  })

  it('says how many lines wait while the invoice is to check', () => {
    const lines = [entry({ line: 1, cont: '704' }), entry({ line: 2 }), entry({ line: 3 })]

    expect(listAccount(invoice({ line_accounts: lines }))).toEqual({ main: '704', more: '2 linii fără cont' })
    expect(listAccount(invoice({ line_accounts: [entry({ line: 1 })] }))).toEqual({ main: null, more: 'o linie fără cont' })
    expect(listAccount(invoice({ line_accounts: [entry({ line: 1 }), entry({ line: 2, method: 'follows' })] })))
      .toEqual({ main: null, more: 'o linie fără cont' })
  })
})

describe('the largest line', () => {
  it('is the one worth most whatever its sign, the first of equals, as the program decides it', () => {
    expect(largestLine([{ number: 1, value: '40.00' }, { number: 2, value: '-450.00' }, { number: 3, value: '100' }])).toBe(2)
    expect(largestLine([{ number: 1, value: '10' }, { number: 2, value: '10.00' }])).toBe(1)
    expect(largestLine([])).toBeNull()
  })
})
