import { describe, expect, it } from 'vitest'
import {
  clientTabs, confirmedToast, countsLine, importTitle, importedLine, searchForTab, sourceLabel, tabFrom, unmarkedLine,
} from './archiveTexts'

const NOW = new Date('2026-11-17T12:00:00')

describe('the tabs of a client\'s screen', () => {
  it('reads the tab from the address, the received invoices when it says nothing', () => {
    expect(tabFrom(new URLSearchParams('fel=arhiva&import=12'))).toBe('archive')
    expect(tabFrom(new URLSearchParams('fel=emise'))).toBe('issued')
    expect(tabFrom(new URLSearchParams(''))).toBe('received')
    expect(searchForTab('archive')).toEqual({ fel: 'arhiva' })
    expect(searchForTab('issued')).toEqual({ fel: 'emise' })
    expect(searchForTab('received')).toEqual({})
  })

  it('counts each tab once what it counts is known', () => {
    expect(clientTabs(7, 3, 2).map((tab) => tab.label)).toEqual(['Facturi primite (7)', 'Facturi emise (3)', 'Arhivă (2)'])
    expect(clientTabs(undefined, undefined, undefined).map((tab) => tab.label)).toEqual(['Facturi primite', 'Facturi emise', 'Arhivă'])
    expect(clientTabs(7, 3, 0).at(-1)?.value).toBe('archive')
  })
})

describe('an import in the archive', () => {
  it('is named by when it was confirmed and by whom', () => {
    expect(importTitle('2026-11-17T10:42:00', NOW)).toBe('Import de azi, 10:42')
    expect(importTitle('2026-11-14T16:05:00', NOW)).toBe('Import din 14.11.2026, 16:05')
    expect(sourceLabel('api')).toBe('Din automatizare')
    expect(sourceLabel('screen')).toBe('De pe ecran')
  })

  it('says how many invoices it held, of which kind, and whether each had its own file', () => {
    expect(countsLine({ invoices: 12, received: 7, issued: 5, files: 1 })).toBe('12 facturi: 7 primite, 5 emise')
    expect(countsLine({ invoices: 2, received: 1, issued: 1, files: 1 })).toBe('2 facturi: o primită, o emisă')
    expect(countsLine({ invoices: 4, received: 4, issued: 0, files: 1 })).toBe('4 facturi primite')
    expect(countsLine({ invoices: 1, received: 0, issued: 1, files: 1 })).toBe('o factură emisă')
    expect(countsLine({ invoices: 3, received: 3, issued: 0, files: 3 })).toBe('3 facturi primite, câte un fișier pentru fiecare')
    expect(countsLine({ invoices: 25, received: 25, issued: 0, files: 1 })).toBe('25 de facturi primite')
  })

  it('says when invoices of it are no longer marked as imported', () => {
    expect(unmarkedLine(0)).toBeNull()
    expect(unmarkedLine(1)).toBe('O factură nu mai este marcată ca importată, așa că este din nou în fișierul pentru SAGA.')
    expect(unmarkedLine(3)).toBe('3 facturi nu mai sunt marcate ca importate, așa că sunt din nou în fișierul pentru SAGA.')
  })
})

describe('around the confirmation', () => {
  it('says on an invoice\'s screen when it went to SAGA', () => {
    expect(importedLine({ id: 4, imported_at: '2026-11-17T10:42:00', source: 'api' }, NOW)).toBe('Importată în SAGA azi, la 10:42, din automatizare.')
    expect(importedLine({ id: 4, imported_at: '2026-11-16T09:00:00', source: 'screen' }, NOW)).toBe('Importată în SAGA ieri, la 09:00, de pe ecran.')
    expect(importedLine({ id: 4, imported_at: '2026-11-14T16:05:00', source: 'api' }, NOW)).toBe('Importată în SAGA pe 14.11.2026, la 16:05, din automatizare.')
  })

  it('says what was marked and that the file is in the archive', () => {
    expect(confirmedToast(12, 1)).toBe('Cele 12 facturi sunt marcate ca importate. Fișierul este acum în arhivă.')
    expect(confirmedToast(1, 1)).toBe('Factura este marcată ca importată. Fișierul este acum în arhivă.')
    expect(confirmedToast(3, 3)).toBe('Cele 3 facturi sunt marcate ca importate. Fișierele sunt acum în arhivă.')
    expect(confirmedToast(20, 1)).toBe('Cele 20 de facturi sunt marcate ca importate. Fișierul este acum în arhivă.')
  })
})
