// Dates, amounts and percentages as a Romanian reader expects them.

const DAY = new Intl.DateTimeFormat('ro-RO', { day: '2-digit', month: '2-digit', year: 'numeric' })
const TIME = new Intl.DateTimeFormat('ro-RO', { hour: '2-digit', minute: '2-digit' })
const MONTH = new Intl.DateTimeFormat('ro-RO', { month: 'long', year: 'numeric' })

/**
 * "09.11.2026" from "2026-11-09" or a full timestamp. An invoice's date is whatever the
 * supplier's program wrote (it may carry a time zone, "2026-11-09+02:00"), so only its
 * first ten characters are read, and anything unreadable is shown as it is.
 */
export function formatDate(iso: string | null): string {
  if (!iso) return ''
  const [, year, month, day] = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso) ?? []
  return year ? `${day}.${month}.${year}` : iso
}

/** "azi, 09:30", "ieri, 16:02" or "09.11.2026, 14:02". */
export function formatWhen(iso: string | null, now = new Date()): string {
  if (!iso) return 'niciodată'
  const moment = new Date(iso)
  const daysAgo = Math.round((startOfDay(now) - startOfDay(moment)) / 86_400_000)
  const day = daysAgo === 0 ? 'azi' : daysAgo === 1 ? 'ieri' : DAY.format(moment)
  return `${day}, ${TIME.format(moment)}`
}

/** The same moment after a noun ("copia …"): "de azi, 09:30", "de ieri, 16:02" or "din 09.11.2026, 14:02". */
export function formatFromWhen(iso: string, now = new Date()): string {
  const when = formatWhen(iso, now)
  // Romanian says "de azi" and "de ieri", but "din" before a date.
  return `${/^\d/.test(when) ? 'din' : 'de'} ${when}`
}

const WEEKDAY = new Intl.DateTimeFormat('ro-RO', { weekday: 'long' })

/** A moment still to come: "azi, la 14:00", "mâine, la 08:00" or "miercuri, 18.11.2026, la 08:00". */
export function formatNext(iso: string, now = new Date()): string {
  const moment = new Date(iso)
  const daysAhead = Math.round((startOfDay(moment) - startOfDay(now)) / 86_400_000)
  const day = daysAhead === 0 ? 'azi' : daysAhead === 1 ? 'mâine' : `${WEEKDAY.format(moment)}, ${DAY.format(moment)}`
  return `${day}, la ${TIME.format(moment)}`
}

function startOfDay(moment: Date): number {
  return new Date(moment.getFullYear(), moment.getMonth(), moment.getDate()).getTime()
}

/** "1.071,00 lei" from "1071.00"; other currencies keep their code. */
export function formatMoney(amount: string | null | undefined, currency: string | null = 'RON'): string {
  if (amount == null || amount === '') return ''
  const number = Number(amount).toLocaleString('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return `${number} ${!currency || currency === 'RON' ? 'lei' : currency}`
}

/** A quantity the Romanian way: "30", "7,5". */
export function formatNumber(amount: string | null): string {
  return amount === null ? '' : Number(amount).toLocaleString('ro-RO', { maximumFractionDigits: 4 })
}

/** A price or a value without its currency: "28,00", "0,1234". */
export function formatAmount(amount: string | null): string {
  if (amount === null) return ''
  return Number(amount).toLocaleString('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
}

/** Jev costs a few thousandths of a cent per invoice, so small sums keep their first two digits. */
export function formatUsd(amount: number | null): string {
  if (amount === null) return ''
  const options =
    amount === 0 || Math.abs(amount) >= 0.01
      ? { minimumFractionDigits: 2, maximumFractionDigits: 2 }
      : { maximumSignificantDigits: 2 }
  return `${amount.toLocaleString('ro-RO', options)} $`
}

export function formatPercent(fraction: number | null): string {
  return fraction === null ? '' : `${Math.round(fraction * 100)}%`
}

/** A cost period as the program names it ("2026-11", "2026-W45", "2026-11-09", "2026") in words. */
export function formatPeriod(period: string): string {
  if (/^\d{4}-\d{2}-\d{2}$/.test(period)) return formatDate(period)
  if (/^\d{4}-\d{2}$/.test(period)) return capitalise(MONTH.format(new Date(`${period}-01`)))
  const week = /^(\d{4})-W(\d{2})$/.exec(period)
  return week ? `Săptămâna ${Number(week[2])} din ${week[1]}` : period
}

function capitalise(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** "41 MB" or "850 KB": how much room a file takes. */
export function formatSize(bytes: number): string {
  const megabytes = bytes / (1024 * 1024)
  return megabytes >= 1 ? `${Math.round(megabytes).toLocaleString('ro-RO')} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`
}

/** "09:31:07" from a moment the program wrote, in the PC's own time. */
export function formatClock(iso: string): string {
  return iso.slice(11, 19)
}

/** Today as the date fields and the API write it: "2026-11-13". */
export function today(now = new Date()): string {
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10)
}

/** "o factură", "3 facturi", "25 de facturi": Romanian adds "de" from twenty upwards. */
export function countOf(count: number, one: string, many: string): string {
  if (count === 1) return one
  const needsDe = count % 100 >= 20 || (count >= 100 && count % 100 === 0)
  return `${count} ${needsDe ? 'de ' : ''}${many}`
}

/** A long path cut to its last two parts ("…\\data\\SAGA Import"), which say where it is. */
export function shortPath(path: string): string {
  const separator = path.includes('\\') ? '\\' : '/'
  const parts = path.split(/[\\/]/).filter(Boolean)
  return parts.length <= 3 ? path : `…${separator}${parts.slice(-2).join(separator)}`
}

/** The folder a file is in: its path without the last part, with either kind of slash. */
export function folderOf(path: string): string {
  return path.replace(/[\\/][^\\/]*$/, '')
}

/** The day `days` days before today, as the date fields write it. Counted on the calendar: a day is not always 24 hours. */
export function daysAgo(days: number, now = new Date()): string {
  return today(new Date(now.getFullYear(), now.getMonth(), now.getDate() - days, 12))
}
