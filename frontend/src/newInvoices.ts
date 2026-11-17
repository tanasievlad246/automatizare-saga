import { countOf } from './format'

/**
 * What a download brought, in words: received and issued invoices named apart when issued
 * ones came ("3 facturi primite noi", "2 emise noi"), as before when only received ones did
 * ("3 facturi noi"), nothing when nothing came. The download window, the journal and the
 * screen of the automatic download all say it this way.
 */
export function newInvoices(received: number, issued: number): string[] {
  if (issued > 0) {
    return [
      received > 0 ? countOf(received, 'o factură primită nouă', 'facturi primite noi') : 'nicio factură primită',
      countOf(issued, 'o emisă nouă', 'emise noi'),
    ]
  }
  return received > 0 ? [countOf(received, 'o factură nouă', 'facturi noi')] : []
}
