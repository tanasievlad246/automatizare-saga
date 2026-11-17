import { countOf } from '../format'
import type { Client } from '../types'

/**
 * What is new for a client, as badges. Received and issued invoices are named apart once
 * the client has new issued ones; until then it reads as before: "3 facturi noi".
 */
export function newBadges(client: Pick<Client, 'new_count' | 'issued_new_count'>): string[] {
  if (client.issued_new_count === 0) {
    return client.new_count ? [countOf(client.new_count, 'o factură nouă', 'facturi noi')] : []
  }
  return [
    client.new_count ? countOf(client.new_count, 'o primită nouă', 'primite noi') : null,
    countOf(client.issued_new_count, 'o emisă nouă', 'emise noi'),
  ].filter((badge): badge is string => badge !== null)
}

/** The list a client's invoices to check are in: the received one while any of those waits. */
export function reviewLink(client: Pick<Client, 'cui' | 'review_count' | 'issued_review_count'>): string {
  const onlyIssued = client.review_count > 0 && client.review_count === client.issued_review_count
  return `/clienti/${client.cui}?${onlyIssued ? 'fel=emise&' : ''}arata=de-verificat`
}

/** Beside the CUI on the client list: how many invoices of each kind, once the client has issued ones. */
export function countsLine(client: Pick<Client, 'invoices' | 'issued_count'>): string | null {
  if (client.issued_count === 0) return null
  const issued = client.issued_count === 1 ? 'una emisă' : countOf(client.issued_count, '', 'emise')
  return `${countOf(client.invoices, 'o factură primită', 'facturi primite')} · ${issued}`
}
