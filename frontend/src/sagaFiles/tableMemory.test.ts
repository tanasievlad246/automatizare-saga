import { describe, expect, it } from 'vitest'
import { recallTable, rememberTable } from './tableMemory'

describe('how a file\'s table was left', () => {
  it('starts in the order of the file, at the first page, with no invoice open', () => {
    expect(recallTable('12345674/F_never-seen.xml')).toEqual({ sort: null, page: 1, open: [] })
  })

  it('is found again as it was left: the order, the page and the invoices that were open', () => {
    rememberTable('12345674/F_a.xml', { sort: { column: 'total', direction: 'desc' }, page: 2, open: ['3001', '3004'] })

    expect(recallTable('12345674/F_a.xml')).toEqual({ sort: { column: 'total', direction: 'desc' }, page: 2, open: ['3001', '3004'] })
  })

  it('keeps each file of each client apart', () => {
    rememberTable('12345674/F_b.xml', { sort: null, page: 3, open: [] })
    rememberTable('14399840/F_b.xml', { sort: null, page: 1, open: ['4001'] })

    expect(recallTable('12345674/F_b.xml').page).toBe(3)
    expect(recallTable('14399840/F_b.xml').open).toEqual(['4001'])
  })

  it('gives a copy, so what is done with it does not change what is kept', () => {
    rememberTable('12345674/F_c.xml', { sort: null, page: 1, open: ['3001'] })
    recallTable('12345674/F_c.xml').open.push('9999')

    expect(recallTable('12345674/F_c.xml').open).toEqual(['3001'])
  })

  it('forgets a table put back as it starts', () => {
    rememberTable('12345674/F_d.xml', { sort: { column: 'date', direction: 'asc' }, page: 1, open: [] })
    rememberTable('12345674/F_d.xml', { sort: null, page: 1, open: [] })

    expect(recallTable('12345674/F_d.xml')).toEqual({ sort: null, page: 1, open: [] })
  })
})
