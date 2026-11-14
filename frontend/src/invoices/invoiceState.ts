import type { Invoice } from '../types'

/** Waiting for a person to choose its account. One already imported in SAGA no longer is. */
export function needsAnAccount(invoice: Invoice): boolean {
  return invoice.classification_status === 'review' && !invoice.uploaded_to_accounting
}
