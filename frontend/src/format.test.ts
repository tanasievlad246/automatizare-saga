import { describe, expect, it } from 'vitest'
import { ApiError } from './api'
import { errorDetail, errorMessage } from './errorMessages'
import {
  countOf, daysAgo, formatAmount, formatDate, formatFromWhen, formatMoney, formatNext, formatPercent, formatPeriod, formatUsd, formatSize, formatWhen,
  shortPath, today,
} from './format'

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
    expect(errorMessage(new ApiError('something_new', 'x'))).toContain('A apărut o problemă în program.')
    expect(errorMessage(new Error('boom'))).toContain('A apărut o problemă în program.')
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

describe('a long folder path', () => {
  it('keeps its last two parts, which say where it is', () => {
    expect(shortPath('C:\\Users\\Maria\\AppData\\Local\\AutoSaga\\data\\SAGA Import')).toBe('…\\data\\SAGA Import')
    expect(shortPath('/Users/maria/Projects/demo/data/SAGA Import')).toBe('…/data/SAGA Import')
  })

  it('is left alone when it is short already', () => {
    expect(shortPath('C:\\SAGA Import')).toBe('C:\\SAGA Import')
    expect(shortPath('E:\\Copii\\AutoSaga')).toBe('E:\\Copii\\AutoSaga')
    expect(shortPath('')).toBe('')
  })
})

describe('a moment said after a noun ("copia …")', () => {
  it('takes "de" before today and yesterday, and "din" before a date', () => {
    const now = new Date('2026-11-13T15:00:00')
    expect(formatFromWhen('2026-11-13T09:30:00', now)).toBe('de azi, 09:30')
    expect(formatFromWhen('2026-11-12T16:02:00', now)).toBe('de ieri, 16:02')
    expect(formatFromWhen('2026-11-09T14:02:00', now)).toBe('din 09.11.2026, 14:02')
  })
})

describe('a failure that means something else in one place', () => {
  const HERE = { backup_error: 'Restaurarea nu a putut începe: copia nu mai este în folder.' }

  it('is said in that place’s own words', () => {
    expect(errorMessage(new ApiError('backup_error', 'Snapshot not found.'), HERE)).toBe(HERE.backup_error)
  })

  it('keeps the usual sentence for every other code', () => {
    expect(errorMessage(new ApiError('busy', 'A sync is running.'), HERE)).toContain('Se descarcă deja facturi')
    expect(errorMessage(new ApiError('backup_error', 'x'))).toContain('Copia de siguranță nu a reușit')
    expect(errorMessage(new Error('boom'), HERE)).toContain('A apărut o problemă în program.')
  })

  it('keeps the program’s own words as the detail', () => {
    expect(errorDetail(new ApiError('internal_error', 'No such drive: E:'))).toBe('No such drive: E:')
    expect(errorDetail('boom')).toBe('boom')
  })
})

describe('the size of a file', () => {
  it('is in megabytes, or kilobytes when small', () => {
    expect(formatSize(41 * 1024 * 1024)).toBe('41 MB')
    expect(formatSize(850 * 1024)).toBe('850 KB')
    expect(formatSize(12)).toBe('1 KB')
  })
})

describe('the next download', () => {
  const now = new Date(2026, 10, 15, 9, 0)
  it('says today, tomorrow, or the weekday and date', () => {
    expect(formatNext('2026-11-15T14:00:00', now)).toBe('azi, la 14:00')
    expect(formatNext('2026-11-16T08:00:00', now)).toBe('mâine, la 08:00')
    expect(formatNext('2026-11-18T08:00:00', now)).toBe('miercuri, 18.11.2026, la 08:00')
  })
})

describe('days as the date fields write them', () => {
  it('writes the day the PC is in, also just after midnight', () => {
    expect(today(new Date(2026, 10, 16, 0, 5))).toBe('2026-11-16')
    expect(today(new Date(2026, 10, 16, 23, 55))).toBe('2026-11-16')
  })

  it('counts days back on the calendar, across months and the change of the clock', () => {
    expect(daysAgo(60, new Date(2026, 10, 16, 9, 0))).toBe('2026-09-17')
    expect(daysAgo(1, new Date(2026, 2, 29, 0, 30))).toBe('2026-03-28')
    expect(daysAgo(1, new Date(2026, 9, 25, 23, 30))).toBe('2026-10-24')
    expect(daysAgo(0, new Date(2026, 10, 16, 9, 0))).toBe('2026-11-16')
  })
})
