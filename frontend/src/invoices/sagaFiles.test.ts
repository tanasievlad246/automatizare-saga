import { describe, expect, it } from 'vitest'
import type { Invoice, SagaState } from '../types'
import { fileCardNote, importedButton, isStale, NOT_UP_TO_DATE, placeLine, readyPlaces, SAGA_WAYS } from './sagaFiles'

const invoice = (id: string, path: string | null, more: Partial<Invoice> = {}) =>
  ({ id, saga_xml_path: path, classification_status: 'classified', uploaded_to_accounting: false, ...more }) as Invoice

const FOLDER = 'C:\\AutoSaga\\SAGA Import\\12345674'
const FILE = `${FOLDER}\\F_1_A1_03.11.2026.xml`
const fine = (file_per: SagaState['file_per'] = 'client'): SagaState => ({ file_per, written_at: null, problem: null })
const broken: SagaState = { ...fine(), problem: { message: 'PermissionError', at: '2026-11-16T10:02:00+02:00' } }

describe('where the ready invoices are', () => {
  it('is one file when the client has one file for all of them', () => {
    const places = readyPlaces([invoice('1', FILE), invoice('2', FILE)], 'client')

    expect(places).toEqual([{ path: FILE, invoices: [expect.objectContaining({ id: '1' }), expect.objectContaining({ id: '2' })] }])
  })

  it('is the folder when every invoice has its own file', () => {
    const places = readyPlaces([invoice('1', FILE), invoice('2', `${FOLDER}\\F_1_A2_03.11.2026.xml`)], 'invoice')

    expect(places.map((place) => [place.path, place.invoices.length])).toEqual([[FOLDER, 2]])
  })
})

describe('whether the folder can be trusted', () => {
  it('can when nothing went wrong and every ready invoice is in a file', () => {
    expect(isStale([invoice('1', FILE)], fine())).toBe(false)
    expect(isStale([], fine())).toBe(false)
  })

  it('cannot while the program could not bring it up to date', () => {
    expect(isStale([invoice('1', FILE)], broken)).toBe(true)
    expect(isStale([], broken)).toBe(true)
  })

  it('cannot while a ready invoice is in no file: marking it would tick an invoice SAGA never got', () => {
    expect(isStale([invoice('1', FILE), invoice('2', null)], fine())).toBe(true)
  })
})

describe('what the card says', () => {
  it('counts the invoices of a file', () => {
    expect(placeLine(12, 'client')).toBe('12 facturi gata sunt într-un singur fișier:')
    expect(placeLine(25, 'client')).toBe('25 de facturi gata sunt într-un singur fișier:')
    expect(placeLine(1, 'client')).toBe('O factură gata este în fișierul de mai jos:')
  })

  it('counts the invoices of a folder', () => {
    expect(placeLine(12, 'invoice')).toBe('12 facturi gata sunt în folderul de mai jos, fiecare în fișierul ei:')
    expect(placeLine(1, 'invoice')).toBe('O factură gata este în folderul de mai jos, în fișierul ei:')
  })

  it('names the count on the button, so a difference from what SAGA imported is seen', () => {
    expect(importedButton(1)).toBe('Da, am importat factura')
    expect(importedButton(12)).toBe('Da, am importat cele 12 facturi')
    expect(importedButton(120)).toBe('Da, am importat cele 120 de facturi')
  })

  it('speaks of the folder when it is not up to date: a file may be missing, old, or one too many', () => {
    expect(NOT_UP_TO_DATE.title).toBe('Folderul pentru SAGA nu este la zi')
    expect(NOT_UP_TO_DATE.retry).toBe('Încearcă din nou')
  })

  it('offers exactly two ways, one file per client first', () => {
    expect(SAGA_WAYS.map((way) => way.value)).toEqual(['client', 'invoice'])
  })
})

describe('the note on an invoice decided line by line', () => {
  it('says the invoice waits for every line to have an account', () => {
    const lines = [{ line: 1, cont: '605' }, { line: 2, cont: null }] as Invoice['line_accounts']

    expect(fileCardNote(invoice('1', null, { classification_status: 'review', line_accounts: lines }), fine()))
      .toBe('Factura intră în fișierul pentru SAGA imediat ce toate liniile au un cont.')
  })
})

describe('the note on an invoice', () => {
  it('says the invoice shares the file of its client', () => {
    expect(fileCardNote(invoice('1', FILE), fine())).toBe('Factura este în fișierul clientului, împreună cu celelalte facturi gata de import:')
  })

  it('says nothing more when the file is the invoice’s own', () => {
    expect(fileCardNote(invoice('1', FILE), fine('invoice'))).toBeNull()
  })

  it('says where SAGA puts an invoice whose supplier is the client', () => {
    const sold = { message_type: 'FACTURA TRIMISA', cui: '12345674', supplier_cui: 'RO12345674' }
    expect(fileCardNote(invoice('1', FILE, sold), fine())).toBe(
      'Factura este în fișierul clientului, împreună cu celelalte facturi gata de import. În SAGA ajunge în „Ieșiri”:',
    )
    expect(fileCardNote(invoice('1', FILE, sold), fine('invoice'))).toBe('În SAGA ajunge în „Ieșiri”.')
  })

  it('goes by the supplier, not by what ANAF listed the invoice as', () => {
    const listedAsIssued = { message_type: 'FACTURA TRIMISA', cui: '12345674', supplier_cui: 'RO87654321' }
    expect(fileCardNote(invoice('1', FILE, listedAsIssued), fine())).toBe(
      'Factura este în fișierul clientului, împreună cu celelalte facturi gata de import:',
    )
  })

  it('warns, whatever else is true, while the client’s folder is not up to date', () => {
    const warning = 'Folderul pentru SAGA al acestui client nu este la zi, așa că fișierul poate să nu arate ce vedeți aici. Deschideți lista de facturi a clientului și apăsați acolo „Încearcă din nou”.'

    expect(fileCardNote(invoice('1', FILE), broken)).toBe(warning)
    expect(fileCardNote(invoice('1', null), broken)).toBe(warning)
  })

  it('says an imported invoice is in no file, and how it comes back', () => {
    expect(fileCardNote(invoice('1', null, { uploaded_to_accounting: true }), fine())).toBe(
      'Factura este marcată ca importată, așa că nu mai este în fișierul pentru SAGA. Dacă scoateți bifa, intră la loc.',
    )
  })

  it('does not promise a file to a ticked invoice that has no account', () => {
    expect(fileCardNote(invoice('1', null, { uploaded_to_accounting: true, classification_status: 'review' }), fine())).toBe(
      'Factura este marcată ca importată și nu are cont, așa că nu este în fișierul pentru SAGA.',
    )
  })

  it('says a ready invoice without a file is not in it yet', () => {
    expect(fileCardNote(invoice('1', null), fine())).toBe(
      'Factura are cont, dar nu este încă în fișierul pentru SAGA. Deschideți lista de facturi a clientului și apăsați acolo „Încearcă din nou”.',
    )
  })

  it('says an invoice without an account enters the file once it has one', () => {
    expect(fileCardNote(invoice('1', null, { classification_status: 'review' }), fine())).toBe(
      'Factura intră în fișierul pentru SAGA imediat ce are un cont.',
    )
  })
})
