import { describe, expect, it } from 'vitest'
import type { Invoice } from '../types'
import { isIssued, issuedSummary, whenNoneReceived } from './issuedInvoices'

const invoice = (message_type: string) => ({ message_type }) as Invoice

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
