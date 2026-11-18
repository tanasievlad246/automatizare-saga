import { formatUsd } from '../format'

/**
 * Under the average cost of an invoice, when it is under one cent and so shown as "< 0,01 $":
 * what a thousand invoices cost, a figure that can be read and compared.
 */
export function perThousandLine(average: number | null): string | null {
  if (average === null || average <= 0 || average >= 0.01) return null
  return `La ${(1000).toLocaleString('ro-RO')} de facturi: ${formatUsd(average * 1000)}`
}
