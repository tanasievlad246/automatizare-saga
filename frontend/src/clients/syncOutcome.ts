import { countOf } from '../format'
import type { SyncResult } from '../types'

/**
 * What one client's download brought, in a sentence. It must never read as a success when
 * something was left behind, and it says when more days were searched than were asked for.
 */
export function describeSyncResult(result: SyncResult, askedDays: number | null): string {
  const parts = [result.new_count === 0 ? 'nimic nou' : countOf(result.new_count, 'o factură nouă', 'facturi noi')]
  const toReview = result.classification?.review ?? 0
  if (toReview) parts.push(`${toReview} de verificat`)
  if (result.failed_count) {
    const failed = result.failed_count === 1 ? 'una nu s-a putut descărca' : `${result.failed_count} nu s-au putut descărca`
    parts.push(`${failed} (încercați din nou mai târziu)`)
  }
  if (askedDays !== null && result.window_days > askedDays) {
    parts.push(`am căutat în ultimele ${countOf(result.window_days, 'zi', 'zile')}, de la ultima descărcare`)
  }
  return parts.join(', ')
}
