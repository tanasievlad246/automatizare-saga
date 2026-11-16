import { countOf } from '../format'
import type { SyncResult } from '../types'

/**
 * What one client's download brought, in a sentence. It must never read as a success when
 * something was left behind, and it says when more days were searched than were asked for.
 * "New" are the received invoices only: the ones the client issued are counted apart.
 */
export function describeSyncResult(result: SyncResult, askedDays: number | null): string {
  const { received_count: received, issued_count: issued } = result
  const parts = [
    received ? countOf(received, 'o factură nouă', 'facturi noi') : issued ? 'nicio factură primită' : 'nimic nou',
  ]
  const toReview = result.classification?.review ?? 0
  if (toReview) parts.push(`${toReview} de verificat`)
  if (issued) parts.push(countOf(issued, 'o factură emisă', 'facturi emise'))
  if (result.failed_count) {
    const failed = result.failed_count === 1 ? 'una nu s-a putut descărca' : `${result.failed_count} nu s-au putut descărca`
    parts.push(`${failed} (încercați din nou mai târziu)`)
  }
  if (askedDays !== null && result.window_days > askedDays) {
    parts.push(`am căutat în ultimele ${countOf(result.window_days, 'zi', 'zile')}, de la ultima descărcare`)
  }
  return parts.join(', ')
}
