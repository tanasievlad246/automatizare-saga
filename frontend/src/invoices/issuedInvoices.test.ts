import { describe, expect, it } from 'vitest'
import type { Invoice } from '../types'
import { isIssued, kindFrom, kindTabs, kindsLine, misfitReason, whenNoneIssued, whenNoneReceived } from './issuedInvoices'

const invoice = (message_type: string) => ({ message_type }) as Invoice

describe('an invoice the client issued', () => {
  it('is told from a received one by what ANAF calls the message', () => {
    expect(isIssued(invoice('FACTURA TRIMISA'))).toBe(true)
    expect(isIssued(invoice('factura trimisa'))).toBe(true)
    expect(isIssued(invoice('FACTURA PRIMITA'))).toBe(false)
    expect(isIssued(invoice('ERORI FACTURA'))).toBe(false)
  })
})

describe('the two kinds of invoice on a client\'s screen', () => {
  it('are received ones unless the address asks for the issued ones', () => {
    expect(kindFrom(new URLSearchParams())).toBe('received')
    expect(kindFrom(new URLSearchParams('fel=emise'))).toBe('issued')
    expect(kindFrom(new URLSearchParams('fel=altceva'))).toBe('received')
  })

  it('are two tabs, each with how many there are once that is known', () => {
    expect(kindTabs(48, 12)).toEqual([
      { value: 'received', label: 'Facturi primite (48)' },
      { value: 'issued', label: 'Facturi emise (12)' },
    ])
    expect(kindTabs(undefined, undefined).map((tab) => tab.label)).toEqual(['Facturi primite', 'Facturi emise'])
  })
})

describe('the lists, when they are empty', () => {
  it('ask for a download only when there was none', () => {
    expect(whenNoneReceived(false)).toBe('Nu ați descărcat încă facturi pentru acest client. Apăsați „Descarcă facturile”.')
    expect(whenNoneIssued(false)).toBe('Nu ați descărcat încă facturi pentru acest client. Apăsați „Descarcă facturile”.')
  })

  it('do not say nothing was downloaded after a download that brought none of the kind', () => {
    expect(whenNoneReceived(true)).toBe(
      'Nicio factură primită în perioada descărcată până acum. Pentru zile mai vechi, apăsați „Descarcă facturile” și alegeți zilele.',
    )
    expect(whenNoneIssued(true)).toBe(
      'Nicio factură emisă în perioada descărcată până acum. Pentru zile mai vechi, apăsați „Descarcă facturile” și alegeți zilele.',
    )
  })
})

describe('why an invoice whose parties do not fit waits for a person', () => {
  it('is said in Romanian for each of the program\'s reasons', () => {
    expect(misfitReason('The client invoiced itself. Decide whether this invoice has to be booked, and how.')).toBe(
      'Factura este emisă de client către el însuși. Hotărâți dacă trebuie înregistrată și cum.',
    )
    expect(misfitReason('The supplier on this issued invoice is not the client, so SAGA would not file it among the sales.')).toBe(
      'Furnizorul de pe această factură emisă nu este clientul, așa că SAGA nu ar pune-o la „Ieșiri”. Verificați dacă factura este a acestui client.',
    )
    expect(misfitReason('The client is the supplier of this received invoice, so SAGA would file it among the sales.')).toBe(
      'Clientul este furnizorul acestei facturi primite, așa că SAGA ar pune-o la „Ieșiri”. Verificați dacă factura este a acestui client.',
    )
  })

  it('is nothing for any other reason', () => {
    expect(misfitReason('Jev declined to answer.')).toBeNull()
    expect(misfitReason(null)).toBeNull()
  })
})

describe('the invoices of each kind in the file for SAGA', () => {
  it('are named apart, with where SAGA puts each kind', () => {
    expect(kindsLine(7, 5)).toBe('7 primite și 5 emise. În SAGA, cele primite ajung în „Intrări”, iar cele emise în „Ieșiri”.')
    expect(kindsLine(1, 1)).toBe('Una primită și una emisă. În SAGA, cea primită ajunge în „Intrări”, iar cea emisă în „Ieșiri”.')
    expect(kindsLine(20, 1)).toBe('20 de primite și una emisă. În SAGA, cele primite ajung în „Intrări”, iar cea emisă în „Ieșiri”.')
  })

  it('say only where the issued ones go when there are no received ones', () => {
    expect(kindsLine(0, 3)).toBe('Toate sunt facturi emise: în SAGA ajung în „Ieșiri”.')
    expect(kindsLine(0, 1)).toBe('Este o factură emisă: în SAGA ajunge în „Ieșiri”.')
  })

  it('say nothing more about received invoices alone, as before', () => {
    expect(kindsLine(12, 0)).toBeNull()
  })
})
