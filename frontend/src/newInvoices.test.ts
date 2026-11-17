import { describe, expect, it } from 'vitest'
import { newInvoices } from './newInvoices'

describe('what a download brought', () => {
  it('names received and issued invoices apart when issued ones came', () => {
    expect(newInvoices(3, 2)).toEqual(['3 facturi primite noi', '2 emise noi'])
    expect(newInvoices(1, 1)).toEqual(['o factură primită nouă', 'o emisă nouă'])
    expect(newInvoices(0, 20)).toEqual(['nicio factură primită', '20 de emise noi'])
  })

  it('says it as before when only received invoices came', () => {
    expect(newInvoices(3, 0)).toEqual(['3 facturi noi'])
    expect(newInvoices(0, 0)).toEqual([])
  })
})
