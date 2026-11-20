// The technical view of the journal, for whoever looks into how the program works: the
// requests to ANAF and Jev and the program's own records, put among the steps of an operation.

import { countDoing, countOf } from '../format'
import { readableXml } from '../invoices/readableXml'
import type { JournalLine, TechnicalBody, TechnicalRecord } from '../types'
import { LEVEL_NAMES } from './eventTexts'

/** A step of the journal or a technical record, in the order they happened. */
export type TimelineItem = { kind: 'line'; line: JournalLine } | { kind: 'record'; record: TechnicalRecord }

/**
 * The steps and the technical records of one operation, oldest first, each where it happened.
 * Both are read from the newest back, page by page: while one of them still has older ones to
 * read, nothing older than its oldest read is shown, or a part of the operation would seem to
 * have had no requests (or no steps) when they are only not read yet.
 */
export function timeline(
  lines: JournalLine[], allLinesRead: boolean, unordered: TechnicalRecord[], allRecordsRead: boolean,
): TimelineItem[] {
  const records = [...unordered].sort((a, b) => (a.at === b.at ? a.id - b.id : later(a.at, b.at) ? 1 : -1))
  const limits = [
    ...(allLinesRead || !lines.length ? [] : [lines[0].at]),
    ...(allRecordsRead || !records.length ? [] : [records[0].at]),
  ]
  const from = limits.reduce((latest, at) => (later(at, latest) ? at : latest), '')
  const items: TimelineItem[] = []
  let next = 0
  for (const line of lines) {
    // A record written at the same moment as a step comes first: the step tells of what it did.
    while (next < records.length && !later(records[next].at, line.at)) items.push({ kind: 'record', record: records[next++] })
    items.push({ kind: 'line', line })
  }
  while (next < records.length) items.push({ kind: 'record', record: records[next++] })
  return items.filter((item) => !later(from, item.kind === 'line' ? item.line.at : item.record.at))
}

/**
 * Is `a` later than `b`? Both are written by the program in the PC's own time, so they compare
 * as text; one without its fraction of a second ("…:58+02:00") sorts before "…:58.1+02:00".
 */
function later(a: string, b: string): boolean {
  return a > b
}

/** How an answer looks: worked, refused or limited by the other side, or failed or never came. */
export function statusLook(record: TechnicalRecord): 'ok' | 'limited' | 'failed' {
  const status = record.status
  if (status === null || status === undefined || status >= 500) return 'failed'
  return status >= 400 ? 'limited' : 'ok'
}

/** The address without "https://": the host and the path are what tell two requests apart. */
export function shortAddress(url: string): string {
  return url.replace(/^https?:\/\//, '')
}

/** "312 B", "1,2 kB", "148 kB", "2,4 MB". */
export function formatBytes(bytes: number): string {
  const decimal = (value: number) => value.toLocaleString('ro-RO', { maximumFractionDigits: value < 10 ? 1 : 0 })
  if (bytes < 1000) return `${bytes} B`
  if (bytes < 1024 * 1000) return `${decimal(bytes / 1024)} kB`
  return `${decimal(bytes / (1024 * 1024))} MB`
}

/** "09:30:58,102": the time with its thousandths, so steps close together can be told apart. */
export function clockFine(at: string): string {
  const fraction = at[19] === '.' ? at.slice(20, 23).padEnd(3, '0') : '000'
  return `${at.slice(11, 19)},${fraction}`
}

/** The level of a program record in Romanian. */
export function recordLevelName(level: TechnicalRecord['level']): string {
  return level === 'debug' ? 'Depanare' : LEVEL_NAMES[level]
}

const SERVICE_NAMES: Record<string, string> = { anaf: 'ANAF', anaf_login: 'ANAF', jev: 'Jev' }

/** To whom a request went, in a word. */
export function serviceName(service: string | undefined): string {
  return (service && SERVICE_NAMES[service]) || service || ''
}

const FORMAT_NAMES: Record<string, string> = { json: 'JSON', xml: 'XML', form: 'Formular', text: 'Text' }

/** A kept body laid out to be read: JSON and XML indented, a form one field a line. Anything else as it came. */
export function readableBody(body: TechnicalBody): string {
  if (!('text' in body)) return ''
  if (body.format === 'json') {
    try {
      return JSON.stringify(JSON.parse(body.text), null, 2)
    } catch {
      return body.text // cut short, it is no longer JSON
    }
  }
  if (body.format === 'xml') return readableXml(body.text)
  if (body.format === 'form') return body.text.split('&').join('\n')
  return body.text
}

/** What a body is, in a line: its kind and size, or why it was not kept. */
export function bodyNote(body: TechnicalBody): string {
  if ('empty' in body) return 'Fără conținut.'
  if ('binary' in body) {
    return `Conținut binar (${[body.type, formatBytes(body.bytes)].filter(Boolean).join(', ')}): nu se păstrează, doar mărimea lui.`
  }
  if ('too_large' in body) return `Conținut prea mare (${formatBytes(body.bytes)}): nu se păstrează.`
  const kind = `${FORMAT_NAMES[body.format] ?? body.format}, ${formatBytes(body.bytes)}`
  return body.cut ? `${kind}. Tăiat: s-au păstrat primele ${formatBytes(body.text.length)}.` : kind
}

/** "4 cereri, una cu eroare, 11 rânduri din program": what an operation holds on the technical side. */
export function countsText(counts: { http: number; problems: number; log: number } | undefined): string {
  if (!counts) return ''
  return [
    counts.http ? countOf(counts.http, 'o cerere', 'cereri') : '',
    counts.problems ? countDoing(counts.problems, 'una cu eroare', 'cu eroare') : '',
    counts.log ? countOf(counts.log, 'un rând din program', 'rânduri din program') : '',
  ].filter(Boolean).join(', ')
}

/** The strip over an operation's steps: to whom it spoke, what went wrong, and from when to when. */
export function operationSummary(records: TechnicalRecord[]) {
  if (!records.length) return null
  const calls = records.filter((record) => record.kind === 'http')
  const to = (name: string) => calls.filter((record) => serviceName(record.service) === name).length
  const places = [['ANAF', to('ANAF')], ['Jev', to('Jev')]] as const
  const where = places
    .filter(([, count]) => count > 0)
    .map(([name, count]) => `${count === 1 ? 'una' : count} către ${name}`)
  const problems = calls.filter((record) => statusLook(record) !== 'ok').length
  const logs = records.length - calls.length
  const times = records.map((record) => record.at).sort()
  return {
    requests: calls.length ? `${countOf(calls.length, 'o cerere', 'cereri')}${where.length ? `: ${where.join(', ')}` : ''}` : '',
    problems: problems ? countDoing(problems, 'una cu eroare', 'cu eroare') : '',
    records: logs ? countOf(logs, 'un rând din program', 'rânduri din program') : '',
    from: times[0].slice(11, 19),
    to: times[times.length - 1].slice(11, 19),
  }
}
