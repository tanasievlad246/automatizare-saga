import { describe, expect, it } from 'vitest'
import type { Client } from '../types'
import { countsLine, newBadges, reviewLink } from './clientCounts'

const client = (fields: Partial<Client>) =>
  ({ cui: '12345674', new_count: 0, issued_new_count: 0, review_count: 0, issued_review_count: 0, ...fields }) as Client

describe('what is new for a client', () => {
  it('names the kinds apart once the client has new issued invoices', () => {
    expect(newBadges(client({ new_count: 3, issued_new_count: 2 }))).toEqual(['3 primite noi', '2 emise noi'])
    expect(newBadges(client({ new_count: 1, issued_new_count: 1 }))).toEqual(['o primită nouă', 'o emisă nouă'])
    expect(newBadges(client({ issued_new_count: 20 }))).toEqual(['20 de emise noi'])
  })

  it('says new invoices as before when they are all received ones', () => {
    expect(newBadges(client({ new_count: 3 }))).toEqual(['3 facturi noi'])
    expect(newBadges(client({ new_count: 1 }))).toEqual(['o factură nouă'])
    expect(newBadges(client({}))).toEqual([])
  })
})

describe('the way to the invoices to check', () => {
  it('opens the received list when some received invoice waits', () => {
    expect(reviewLink(client({ review_count: 3, issued_review_count: 1 }))).toBe('/clienti/12345674?arata=de-verificat')
  })

  it('opens the issued list when only issued invoices wait', () => {
    expect(reviewLink(client({ review_count: 2, issued_review_count: 2 }))).toBe('/clienti/12345674?fel=emise&arata=de-verificat')
  })
})

describe('how many invoices a client has', () => {
  it('names both kinds once the client has issued invoices', () => {
    expect(countsLine(client({ invoices: 48, issued_count: 12 }))).toBe('48 de facturi primite · 12 emise')
    expect(countsLine(client({ invoices: 1, issued_count: 1 }))).toBe('o factură primită · una emisă')
  })

  it('says nothing while it has received invoices only, as before', () => {
    expect(countsLine(client({ invoices: 48, issued_count: 0 }))).toBeNull()
  })
})
