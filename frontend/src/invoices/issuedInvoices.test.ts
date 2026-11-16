import { describe, expect, it } from 'vitest'
import type { Invoice } from '../types'
import { MOST_ISSUED_SHOWN, isIssued, issuedSummary, newestFirst, notAllShown, whenNoneReceived } from './issuedInvoices'

const invoice = (message_type: string) => ({ message_type }) as Invoice
const dated = (id: string, invoice_issue_date: string | null) => ({ id, invoice_issue_date }) as Invoice

describe('an invoice the client issued', () => {
  it('is told from a received one by what ANAF calls the message', () => {
    expect(isIssued(invoice('FACTURA TRIMISA'))).toBe(true)
    expect(isIssued(invoice('factura trimisa'))).toBe(true)
    expect(isIssued(invoice('FACTURA PRIMITA'))).toBe(false)
    expect(isIssued(invoice('ERORI FACTURA'))).toBe(false)
  })
})

describe('what the card of issued invoices says', () => {
  it('counts them, and says what the program does not do with them', () => {
    expect(issuedSummary(5)).toBe(
      'Programul a descărcat și 5 facturi emise de acest client. Ele nu primesc cont și nu se scriu pentru SAGA; le puteți doar vedea.',
    )
    expect(issuedSummary(1)).toBe(
      'Programul a descărcat și o factură emisă de acest client. Ea nu primește cont și nu se scrie pentru SAGA; o puteți doar vedea.',
    )
    expect(issuedSummary(25)).toContain('25 de facturi emise')
  })

  it('says so when there is none', () => {
    expect(issuedSummary(0)).toBe('Programul nu a descărcat nicio factură emisă de acest client.')
  })
})

describe('the list of received invoices, when it is empty', () => {
  it('asks for a download only when there was none', () => {
    expect(whenNoneReceived(false)).toBe('Nu ați descărcat încă facturi pentru acest client. Apăsați „Descarcă facturile”.')
  })

  it('does not say nothing was downloaded after a download that brought no received invoice', () => {
    expect(whenNoneReceived(true)).toBe(
      'Nicio factură primită în perioada descărcată până acum. Pentru zile mai vechi, apăsați „Descarcă facturile” și alegeți zilele.',
    )
  })
})

describe('the list of issued invoices', () => {
  it('starts with the newest, by the date on the invoice and then by ANAF\'s number', () => {
    const listed = [dated('3501', '2026-11-06'), dated('10002', '2026-11-12'), dated('9001', '2026-11-12'), dated('3400', null)]

    expect(newestFirst(listed).map((each) => each.id)).toEqual(['10002', '9001', '3501', '3400'])
    expect(listed.map((each) => each.id)).toEqual(['3501', '10002', '9001', '3400']) // the list given is left as it was
  })

  it('says when only the newest are on screen', () => {
    expect(MOST_ISSUED_SHOWN).toBe(200)
    expect(notAllShown(5003)).toBe('Se văd cele mai noi 200 din 5003 facturi emise.')
    expect(notAllShown(200)).toBeNull()
    expect(notAllShown(3)).toBeNull()
  })
})
