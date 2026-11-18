import { describe, expect, it } from 'vitest'
import type { ClassifyAgainResult } from '../types'
import { forWhom, introLine, outcomeLine, startLabel, toCheckLine } from './classifyAgainTexts'

const result = (fields: Partial<ClassifyAgainResult> = {}): ClassifyAgainResult => ({
  ok: true, cui: '12345674', client: 'Alfa Construct SRL', total: 7, classified: 5, review: 2, waiting: 0, skipped: 0,
  jev_asked: true, jev_stopped: false, jev_calls: 4, jev_cost_usd: 0.0123, ...fields,
})

describe('what waits for an account, said above the button', () => {
  it('says what is to check as the client list always has', () => {
    expect(toCheckLine(12, 0)).toBe('12 facturi sunt de verificat: trebuie să le alegeți contul.')
    expect(toCheckLine(1, 0)).toBe('O factură este de verificat: trebuie să îi alegeți contul.')
  })

  it('adds the invoices still waiting for Jev', () => {
    expect(toCheckLine(12, 2)).toBe('12 facturi sunt de verificat: trebuie să le alegeți contul. 2 facturi așteaptă contul de la Jev.')
    expect(toCheckLine(0, 1)).toBe('O factură așteaptă contul: Jev nu a răspuns la ultima descărcare.')
    expect(toCheckLine(0, 3)).toBe('3 facturi așteaptă contul: Jev nu a răspuns la ultima descărcare.')
  })

  it('on a client screen, names the received and the issued ones apart', () => {
    expect(toCheckLine(7, 0, 2)).toBe('7 facturi sunt de verificat: 5 primite și 2 emise.')
    expect(toCheckLine(2, 0, 1)).toBe('2 facturi sunt de verificat: una primită și una emisă.')
    expect(toCheckLine(3, 0, 0)).toBe('3 facturi sunt de verificat.')
    expect(toCheckLine(2, 0, 2)).toBe('2 facturi emise sunt de verificat.')
    expect(toCheckLine(1, 0, 1)).toBe('O factură emisă este de verificat.')
    expect(toCheckLine(1, 1, 0)).toBe('O factură este de verificat. O factură așteaptă contul de la Jev.')
  })
})

describe('the window, before it starts', () => {
  it('names the client, or how many clients', () => {
    expect(forWhom([{ name: 'Alfa Construct SRL', cui: '12345674' }])).toBe('Alfa Construct SRL · CUI 12345674')
    expect(forWhom([{ name: 'A', cui: '1' }, { name: 'B', cui: '2' }, { name: 'C', cui: '3' }, { name: 'D', cui: '4' }]))
      .toBe('La cei 4 clienți cu facturi de verificat')
  })

  it('says what happens, with Jev or without', () => {
    expect(introLine(7, true)).toBe('Cele 7 facturi trec din nou prin regulile dumneavoastră. Pentru ce nu decide nicio regulă este întrebat Jev.')
    expect(introLine(25, false)).toBe('Cele 25 de facturi trec din nou prin regulile dumneavoastră. Jev nu este întrebat.')
    expect(introLine(1, true)).toBe('Factura trece din nou prin regulile dumneavoastră. Dacă nu o decide nicio regulă, este întrebat Jev.')
    expect(introLine(1, false)).toBe('Factura trece din nou prin regulile dumneavoastră. Jev nu este întrebat.')
  })

  it('names how many invoices the button sends', () => {
    expect(startLabel(7)).toBe('Clasifică din nou cele 7 facturi')
    expect(startLabel(20)).toBe('Clasifică din nou cele 20 de facturi')
    expect(startLabel(1)).toBe('Clasifică din nou factura')
  })
})

describe('how one client went', () => {
  it('says how many got an account, how many are left, and what Jev cost', () => {
    expect(outcomeLine(result())).toBe('5 au primit cont, 2 rămân de verificat · Jev: 4 întrebări, 0,01 $')
    expect(outcomeLine(result({ total: 1, classified: 1, review: 0, jev_calls: 0 }))).toBe('o factură a primit cont')
  })

  it('says plainly when none got an account', () => {
    expect(outcomeLine(result({ total: 3, classified: 0, review: 3, jev_calls: 3, jev_cost_usd: 0.006 })))
      .toBe('nicio factură nu a primit cont; cele 3 rămân de verificat · Jev: 3 întrebări, < 0,01 $')
    expect(outcomeLine(result({ total: 1, classified: 0, review: 1, jev_calls: 1, jev_cost_usd: 0.002 })))
      .toBe('factura rămâne de verificat · Jev: o întrebare, < 0,01 $')
  })

  it('names the invoices still waiting for Jev and those that cannot be read', () => {
    expect(outcomeLine(result({ total: 4, classified: 1, review: 1, waiting: 1, skipped: 1, jev_calls: 0 })))
      .toBe('o factură a primit cont, una rămâne de verificat, una așteaptă încă răspunsul lui Jev, una nu se poate citi și a fost lăsată deoparte')
  })

  it('says when only the rules ran', () => {
    expect(outcomeLine(result({ jev_asked: false, jev_calls: 0 }))).toBe('5 au primit cont, 2 rămân de verificat · doar după reguli')
  })

  it('says when Jev stopped answering, and why it was not asked after that', () => {
    expect(outcomeLine(result({ total: 2, classified: 0, review: 2, jev_stopped: true, jev_calls: 1, jev_cost_usd: 0 })))
      .toBe('nicio factură nu a primit cont; cele 2 rămân de verificat. Jev nu a răspuns, așa că facturile de după au rămas cum erau. Verificați cheia OpenRouter și creditul din cont.')
    expect(outcomeLine(result({ total: 1, classified: 1, review: 0, jev_asked: false, jev_calls: 0 }), true))
      .toBe('o factură a primit cont. Jev nu a mai fost întrebat, fiindcă nu a răspuns la un client de dinainte.')
  })

  it('puts no "de" between a number from twenty up and what the invoices did', () => {
    expect(outcomeLine(result({ total: 65, classified: 25, review: 20, waiting: 20, skipped: 0, jev_calls: 0 })))
      .toBe('25 au primit cont, 20 rămân de verificat, 20 așteaptă încă răspunsul lui Jev')
    expect(outcomeLine(result({ total: 40, classified: 20, review: 0, waiting: 0, skipped: 20, jev_calls: 0 })))
      .toBe('20 au primit cont, 20 nu se pot citi și au fost lăsate deoparte')
    expect(outcomeLine(result({ total: 25, classified: 0, review: 25, jev_calls: 25, jev_cost_usd: 0.05 })))
      .toBe('nicio factură nu a primit cont; cele 25 rămân de verificat · Jev: 25 de întrebări, 0,05 $')
  })

  it('says when a client had nothing left to check', () => {
    expect(outcomeLine(result({ total: 0, classified: 0, review: 0, jev_calls: 0 }))).toBe('nu mai are facturi de verificat.')
  })
})
