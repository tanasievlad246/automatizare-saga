// What the "Descărcare automată" screen and the menu say, written from the schedule's status.

import { ANAF_KEEPS_DAYS } from '../anafKeeps'
import { knowsCode, messageForCode } from '../errorMessages'
import { newInvoices } from '../newInvoices'
import { countOf, daysAgo, formatDate, formatFromWhen, formatNext, formatWhen, today } from '../format'
import type { SchedulePeriod, ScheduleRun, ScheduleStatus } from '../types'

export const DAY_NAMES = ['Luni', 'Marți', 'Miercuri', 'Joi', 'Vineri', 'Sâmbătă', 'Duminică']
/** The most times of day one schedule may hold. */
export const MOST_TIMES = 4
/** The periods offered as buttons: the last so many days. */
export const PERIOD_DAYS = [3, 5, 7, 10]

/** A day as the date fields and the program write it. A year typed with five digits is not one. */
const isDay = (text: string) => /^\d{4}-\d{2}-\d{2}$/.test(text)

const day = (index: number) => DAY_NAMES[index].toLowerCase()

/** "a, b și c" */
function listed(items: string[]): string {
  return items.length < 2 ? items.join('') : `${items.slice(0, -1).join(', ')} și ${items[items.length - 1]}`
}

/** "de luni până vineri, la 08:00" */
export function describeWhen(days: number[], times: string[]): string {
  const sorted = [...days].sort((a, b) => a - b)
  const consecutive = sorted.length >= 3 && sorted[sorted.length - 1] - sorted[0] === sorted.length - 1
  const which =
    sorted.length === 7
      ? 'în fiecare zi'
      : consecutive
        ? `de ${day(sorted[0])} până ${day(sorted[sorted.length - 1])}`
        : listed(sorted.map(day))
  return `${which}, la ${listed(times)}`
}

/**
 * "facturile sosite în ultimele 7 zile" or "facturile sosite în perioada 01.11.2026 – 30.11.2026".
 * "Sosite": ANAF goes by the day an invoice reached it, not by the date written on it.
 */
export function describePeriod(period: SchedulePeriod): string {
  if ('days' in period) return `facturile sosite în ${period.days === 1 ? 'ultima zi' : `ultimele ${countOf(period.days, 'zi', 'zile')}`}`
  const first = formatDate(period.start)
  return period.start === period.end ? `facturile sosite pe ${first}` : `facturile sosite în perioada ${first} – ${formatDate(period.end)}`
}

/** Under the period's fields: what the choice means at each download. */
export function periodSays(period: SchedulePeriod): string {
  if (!('days' in period) && (!isDay(period.start) || !isDay(period.end) || period.start > period.end)) {
    return 'Alegeți prima și ultima zi a perioadei.'
  }
  const each = `La fiecare descărcare, programul aduce ${describePeriod(period)}.`
  return 'days' in period
    ? `${each} Dacă a stat oprit mai mult de atât, merge înapoi până la ultima descărcare completă.`
    : `${each} Perioada rămâne aceeași: după ${formatDate(period.end)} nu mai vin facturi noi până nu alegeți altă perioadă.`
}

export type ScheduleChoice = { enabled: boolean; days: number[]; times: string[]; period: SchedulePeriod }

/** The same schedule, whatever order the days and the times were chosen in. */
export function sameSchedule(a: ScheduleChoice, b: ScheduleChoice): boolean {
  const period = (chosen: SchedulePeriod) => ('days' in chosen ? [chosen.days] : [chosen.start, chosen.end])
  const key = (choice: ScheduleChoice) =>
    JSON.stringify([choice.enabled, [...choice.days].sort((x, y) => x - y), [...choice.times].sort(), period(choice.period)])
  return key(a) === key(b)
}

/** What the form does when the saved schedule is not the one it follows. */
export function onSavedChange(draft: ScheduleChoice, followed: ScheduleChoice, saved: ScheduleChoice): 'nothing' | 'follow' | 'notice' {
  if (sameSchedule(saved, followed)) return 'nothing'
  // A draft equal to the old or to the new saved schedule has no edits to lose.
  return sameSchedule(draft, followed) || sameSchedule(draft, saved) ? 'follow' : 'notice'
}

/** After her own save: has the saved schedule the page shows become her answer yet? */
export function ownSaveArrival(saved: ScheduleChoice, answer: ScheduleChoice, before: ScheduleChoice): 'arrived' | 'waiting' | 'overtaken' {
  if (sameSchedule(saved, answer)) return 'arrived'
  return sameSchedule(saved, before) ? 'waiting' : 'overtaken'
}

/**
 * What keeps the form from being saved, as the program itself would refuse it. The hours and the period's two
 * days are checked even while it is off; the days of the week, and whether ANAF can still be asked for the
 * period, only while it is on.
 */
export function formProblem(enabled: boolean, days: number[], times: string[], period: SchedulePeriod, now = new Date()): string | null {
  if (enabled && days.length === 0) return 'Alegeți cel puțin o zi.'
  if (new Set(times).size < times.length) return 'Aceeași oră apare de două ori.'
  if ('days' in period) return null
  if (!isDay(period.start) || !isDay(period.end)) return 'Alegeți amândouă zilele perioadei.'
  if (period.start > period.end) return 'Prima zi a perioadei este după ultima.'
  if (!enabled) return null
  if (period.start > today(now)) return 'Prima zi a perioadei nu poate fi după azi.'
  if (period.end < daysAgo(ANAF_KEEPS_DAYS, now)) {
    return 'Perioada s-a încheiat de mai mult de 60 de zile, iar ANAF nu mai păstrează facturile din ea.'
  }
  return null
}

export type StateCard = {
  tone: 'done' | 'plain' | 'fresh' | 'attention'; title: string; text: string; journal: boolean; clients: boolean
}

const NOT_DONE_STATUSES: ScheduleRun['status'][] = ['failed', 'unreachable', 'interrupted']

/**
 * The last day of a period of chosen dates that is over, when that is the thing to say: the schedule is on, and
 * the last download did not fail for another reason (one refused over the period itself is the same news).
 */
function endedOn(status: ScheduleStatus, now: Date): string | null {
  const { period, last_run: run } = status
  if (!status.enabled || !('end' in period) || period.end >= today(now)) return null
  const failedOtherwise = run !== null && NOT_DONE_STATUSES.includes(run.status) && run.error?.code !== 'invalid_input'
  return failedOtherwise ? null : period.end
}

/** "3 clienți · 7 facturi primite noi · 4 emise noi · 2 de verificat"; "3 clienți · 7 facturi noi" without issued ones. */
function outcome(run: ScheduleRun): string {
  const came = newInvoices(run.received ?? run.new, run.issued ?? 0)
  const parts = [countOf(run.clients, 'un client', 'clienți'), ...came]
  if (run.review > 0) parts.push(`${run.review} de verificat`)
  if (came.length === 0 && run.review === 0) parts.push('nimic nou')
  return parts.join(' · ')
}

/**
 * What the card at the top of the screen says, first match wins: running, off, no client on, a period that is over
 * (unless the last run failed for another reason), the last run.
 */
export function stateCard(status: ScheduleStatus, now = new Date()): StateCard {
  const card = (tone: StateCard['tone'], title: string, text: string, links: Partial<Pick<StateCard, 'journal' | 'clients'>> = {}): StateCard =>
    ({ tone, title, text, journal: false, clients: false, ...links })
  const { running, last_run: run } = status
  const next = status.next_at ? `Următoarea descărcare: ${formatNext(status.next_at, now)}.` : ''
  const then = (sentence: string) => (next ? `${sentence} ${next}` : sentence)

  if (running) {
    return card(
      'fresh',
      running.total > 1 ? `Se descarcă acum: ${running.done} din ${countOf(running.total, 'un client', 'clienți')}` : 'Se descarcă acum',
      `A început ${formatWhen(running.started_at, now)}. Pagina se schimbă singură când se termină.`,
    )
  }
  if (!status.enabled) {
    return card('plain', 'Descărcarea automată este oprită',
      'Facturile se descarcă doar când apăsați dumneavoastră „Descarcă facturile”, pe pagina Clienți.')
  }
  if (status.clients_on === 0) {
    return card('attention', 'Niciun client nu este pornit',
      'Descărcarea automată nu are ce descărca. Porniți clienții din lista de clienți.', { clients: true })
  }
  const ended = endedOn(status, now)
  if (ended) {
    // Past the 60 days every download is refused, so the next one is not announced.
    const what = ended < daysAgo(ANAF_KEEPS_DAYS, now)
      ? 'ANAF păstrează facturile doar 60 de zile, așa că programul nu mai are ce aduce din perioada aceasta. Alegeți mai jos altă perioadă.'
      : then(`Descărcarea automată mai aduce doar facturile din perioada aceasta. Pentru cele sosite după ${formatDate(ended)}, alegeți mai jos altă perioadă.`)
    return card('attention', `Perioada aleasă s-a încheiat pe ${formatDate(ended)}`, what, { journal: Boolean(run) })
  }
  if (run && NOT_DONE_STATUSES.includes(run.status)) {
    const when = formatFromWhen(run.started_at, now)
    const retry = run.retry_at ? formatNext(run.retry_at, now) : null
    if (run.status === 'failed') {
      const why = !run.error
        ? 'Programul va încerca din nou la următoarea descărcare.'
        : knowsCode(run.error.code)
          ? messageForCode(run.error.code)
          : 'A apărut o problemă în program. Detaliile sunt în jurnal.'
      return card('attention', `Descărcarea ${when} nu a reușit`, then(why), { journal: true })
    }
    if (run.status === 'unreachable') {
      const tries = run.attempt === 1 ? 'o dată' : `de ${run.attempt} ori`
      const what = retry
        ? `Programul mai încearcă ${retry} (încercarea ${run.attempt + 1} din 4).`
        : then(`Programul a încercat ${tries}.`)
      return card('attention', `Descărcarea ${when} nu a ajuns la ANAF`, `Verificați conexiunea la internet. ${what}`, { journal: true })
    }
    const stopped = 'Programul sau calculatorul a fost oprit în timpul ei.'
    return card('attention', `Descărcarea ${when} a fost întreruptă`,
      retry ? `${stopped} Programul o reia ${retry}.` : then(stopped), { journal: true })
  }
  if (run?.status === 'partial') {
    const rest = run.failed_clients > 0
      ? `Pentru ${countOf(run.failed_clients, 'un client', 'clienți')} descărcarea nu a reușit; se reia la următoarea descărcare.`
      : 'Unele facturi nu s-au putut descărca; se reiau la următoarea descărcare.'
    return card('attention', `Ultima descărcare, ${formatWhen(run.started_at, now)}, nu a fost completă`, `${outcome(run)}. ${rest}`, { journal: true })
  }
  const title = next ? `Următoarea descărcare: ${formatNext(status.next_at!, now)}` : 'Descărcarea automată este pornită'
  return run
    ? card('done', title, `Ultima: ${formatWhen(run.started_at, now)} · ${outcome(run)}.`, { journal: true })
    : card('done', title, 'Nu a fost făcută încă nicio descărcare automată.')
}

/** The name of the button that removes a time. */
export function removeTimeName(time: string): string {
  return `Scoate ora ${time}`
}

/** The journal's address: the whole journal, or one operation's own lines. */
export function journalAddress(trace: string | null | undefined): string {
  return trace ? `/jurnal?operatiune=${encodeURIComponent(trace)}` : '/jurnal'
}

/** The first line of the notice on the client list while the program downloads by itself. */
export function runningLine(done: number, total: number): string {
  return total > 1 ? `Programul descarcă acum facturile, singur: ${done} din ${total} clienți.` : 'Programul descarcă acum facturile, singur.'
}

/** Between two reads of the status: did an automatic download end that the lists have not seen? */
export function runEnded(before: ScheduleStatus | undefined, now: ScheduleStatus | undefined): boolean {
  if (!before || !now) return false
  if (before.running && !now.running) return true
  if (now.running) return false
  const finished = now.last_run?.finished_at
  return Boolean(finished) && finished !== before.last_run?.finished_at
}

/** The line under "Descărcare automată" in the menu, only when something needs a look. */
export function menuNote(status: ScheduleStatus | undefined, now = new Date()): { text: string; tone: 'fresh' | 'attention' } | null {
  if (!status) return null
  if (status.running) return { text: 'Se descarcă acum', tone: 'fresh' }
  if (endedOn(status, now)) return { text: 'Perioada s-a încheiat', tone: 'attention' }
  if (status.enabled && status.last_run && NOT_DONE_STATUSES.includes(status.last_run.status)) {
    return { text: 'Ultima nu a reușit', tone: 'attention' }
  }
  return null
}

/** How often the page asks the program again, in milliseconds; false for never. */
export function pollEvery(status: ScheduleStatus | undefined): number | false {
  if (!status) return false
  if (status.running) return 3000
  return status.enabled ? 30000 : false
}
