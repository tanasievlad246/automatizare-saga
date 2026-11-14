import { describe, expect, it } from 'vitest'
import { ApiError } from './api'
import { errorMessage } from './errorMessages'
import { countOf, formatAmount, formatDate, formatMoney, formatPercent, formatPeriod, formatUsd, formatWhen } from './format'

// Intl separates thousands with a narrow no-break space in some places; compare without caring which.
const plain = (text: string) => text.replace(/\s/g, ' ')

describe('amounts', () => {
  it('writes money the Romanian way, with lei for RON', () => {
    expect(plain(formatMoney('1071.00', 'RON'))).toBe('1.071,00 lei')
    expect(plain(formatMoney('119.5', 'EUR'))).toBe('119,50 EUR')
    expect(formatMoney(null)).toBe('')
  })

  it('keeps at least two decimals on a price and at most four', () => {
    expect(formatAmount('28')).toBe('28,00')
    expect(formatAmount('0.12345')).toBe('0,1235')
  })

  it('shows a tiny cost by its first digits instead of rounding it to zero', () => {
    expect(plain(formatUsd(0.00002))).toBe('0,00002 $')
    expect(plain(formatUsd(0.0013))).toBe('0,0013 $')
    expect(plain(formatUsd(0.42))).toBe('0,42 $')
    expect(plain(formatUsd(0))).toBe('0,00 $')
  })

  it('writes a share as a whole percentage', () => {
    expect(formatPercent(0.584)).toBe('58%')
    expect(formatPercent(null)).toBe('')
  })
})

describe('dates', () => {
  it('writes a day as dd.mm.yyyy', () => {
    expect(formatDate('2026-11-09')).toBe('09.11.2026')
    expect(formatDate(null)).toBe('')
  })

  it('says today and yesterday in words', () => {
    const now = new Date('2026-11-13T15:00:00')
    expect(formatWhen('2026-11-13T09:30:00', now)).toBe('azi, 09:30')
    expect(formatWhen('2026-11-12T16:02:00', now)).toBe('ieri, 16:02')
    expect(formatWhen('2026-11-08T14:02:00', now)).toBe('08.11.2026, 14:02')
    expect(formatWhen(null)).toBe('niciodată')
  })

  it('names a cost period in words', () => {
    expect(formatPeriod('2026-11')).toBe('Noiembrie 2026')
    expect(formatPeriod('2026-W45')).toBe('Săptămâna 45 din 2026')
    expect(formatPeriod('2026-11-09')).toBe('09.11.2026')
    expect(formatPeriod('2026')).toBe('2026')
  })
})

describe('counting in Romanian', () => {
  it('uses the singular, the plural, and "de" from twenty upwards', () => {
    expect(countOf(1, 'o factură', 'facturi')).toBe('o factură')
    expect(countOf(3, 'o factură', 'facturi')).toBe('3 facturi')
    expect(countOf(19, 'o zi', 'zile')).toBe('19 zile')
    expect(countOf(20, 'o zi', 'zile')).toBe('20 de zile')
    expect(countOf(101, 'o zi', 'zile')).toBe('101 zile')
    expect(countOf(342, 'o zi', 'zile')).toBe('342 de zile')
  })
})

describe('failures', () => {
  it('are explained in Romanian by their code', () => {
    expect(errorMessage(new ApiError('busy', 'Another sync is running.'))).toContain('Se descarcă deja facturi')
  })

  it('fall back to a general sentence when the code is unknown', () => {
    expect(errorMessage(new ApiError('something_new', 'x'))).toBe('A apărut o problemă în program.')
    expect(errorMessage(new Error('boom'))).toBe('A apărut o problemă în program.')
  })
})

// --- found by the review of the screen ---

import { describeSyncResult } from './clients/syncOutcome'
import { folderOf } from './format'

describe('a date the supplier wrote oddly', () => {
  it('is read from its first ten characters even with a time zone', () => {
    expect(formatDate('2026-11-09+02:00')).toBe('09.11.2026')
    expect(formatDate('2026-11-09T14:02:00+02:00')).toBe('09.11.2026')
  })

  it('is shown as written when it is not a date at all', () => {
    expect(formatDate('09/11/2026')).toBe('09/11/2026')
  })
})

describe('what a download brought', () => {
  const result = { window_days: 5, new_count: 3, failed_count: 0, classification: { classified: 2, review: 1, pending: 0 } }

  it('counts the new invoices and those to check', () => {
    expect(describeSyncResult(result, 5)).toBe('3 facturi noi, 1 de verificat')
    expect(describeSyncResult({ ...result, new_count: 0, classification: null }, 5)).toBe('nimic nou')
  })

  it('never hides invoices that could not be downloaded', () => {
    expect(describeSyncResult({ ...result, new_count: 1, failed_count: 6, classification: null }, 5)).toBe(
      'o factură nouă, 6 nu s-au putut descărca (încercați din nou mai târziu)',
    )
    expect(describeSyncResult({ ...result, new_count: 0, failed_count: 1, classification: null }, 5)).toContain(
      'una nu s-a putut descărca',
    )
  })

  it('says when more days were searched than were asked for', () => {
    expect(describeSyncResult({ ...result, window_days: 21, new_count: 0, classification: null }, 5)).toBe(
      'nimic nou, am căutat în ultimele 21 de zile, de la ultima descărcare',
    )
    expect(describeSyncResult({ ...result, window_days: 3 }, null)).not.toContain('am căutat')
  })
})

describe('the folder of a file', () => {
  it('is its path without the last part, on Windows and elsewhere', () => {
    expect(folderOf('C:\\SAGA Import\\12345674\\F_1_A_09.11.2026.xml')).toBe('C:\\SAGA Import\\12345674')
    expect(folderOf('/data/SAGA Import/12345674/F_1.xml')).toBe('/data/SAGA Import/12345674')
  })
})
