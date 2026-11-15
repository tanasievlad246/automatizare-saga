// What the "Descărcare automată" screen and the menu say, written from the schedule's status.

import { messageForCode } from '../errorMessages'
import { countOf, formatNext, formatWhen } from '../format'
import type { ScheduleRun, ScheduleStatus } from '../types'

export const DAY_NAMES = ['Luni', 'Marți', 'Miercuri', 'Joi', 'Vineri', 'Sâmbătă', 'Duminică']
/** The most times of day one schedule may hold. */
export const MOST_TIMES = 4

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

export type ScheduleChoice = { enabled: boolean; days: number[]; times: string[] }

/** The same schedule, whatever order the days and the times were chosen in. */
export function sameSchedule(a: ScheduleChoice, b: ScheduleChoice): boolean {
  const key = (choice: ScheduleChoice) =>
    JSON.stringify([choice.enabled, [...choice.days].sort((x, y) => x - y), [...choice.times].sort()])
  return key(a) === key(b)
}

/** What keeps the form from being saved. The hours are checked even while it is off; the days only while it is on. */
export function formProblem(enabled: boolean, days: number[], times: string[]): string | null {
  if (enabled && days.length === 0) return 'Alegeți cel puțin o zi.'
  if (times.some((time) => time === '')) return 'Completați ora.'
  if (new Set(times).size < times.length) return 'Aceeași oră apare de două ori.'
  return null
}

export type StateCard = {
  tone: 'done' | 'plain' | 'fresh' | 'attention'; title: string; text: string; journal: boolean; clients: boolean
}

const NOT_DONE_STATUSES: ScheduleRun['status'][] = ['failed', 'unreachable', 'interrupted']

/** "3 clienți · 7 facturi noi · 2 de verificat" */
function outcome(run: ScheduleRun): string {
  const parts = [countOf(run.clients, 'un client', 'clienți')]
  if (run.new > 0) parts.push(countOf(run.new, 'o factură nouă', 'facturi noi'))
  if (run.review > 0) parts.push(`${run.review} de verificat`)
  if (run.new === 0 && run.review === 0) parts.push('nimic nou')
  return parts.join(' · ')
}

/** What the card at the top of the screen says, first match wins: running, off, no client on, the last run. */
export function stateCard(status: ScheduleStatus, now = new Date()): StateCard {
  const card = (tone: StateCard['tone'], title: string, text: string, links: Partial<Pick<StateCard, 'journal' | 'clients'>> = {}): StateCard =>
    ({ tone, title, text, journal: false, clients: false, ...links })
  const { running, last_run: run } = status
  const next = status.next_at ? `Următoarea descărcare: ${formatNext(status.next_at, now)}.` : ''
  const then = (sentence: string) => (next ? `${sentence} ${next}` : sentence)

  if (running) {
    return card(
      'fresh',
      running.total > 0 ? `Se descarcă acum: ${running.done} din ${countOf(running.total, 'un client', 'clienți')}` : 'Se descarcă acum',
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
  if (run && NOT_DONE_STATUSES.includes(run.status)) {
    const when = formatWhen(run.slot, now)
    const retry = run.retry_at ? formatNext(run.retry_at, now) : null
    if (run.status === 'failed') {
      return card('attention', `Descărcarea de ${when} nu a reușit`,
        then(run.error ? messageForCode(run.error.code) : 'Programul va încerca din nou la următoarea descărcare.'), { journal: true })
    }
    if (run.status === 'unreachable') {
      const tries = run.attempt === 1 ? 'o dată' : `de ${run.attempt} ori`
      const what = retry
        ? `Programul mai încearcă ${retry} (încercarea ${run.attempt + 1} din 4).`
        : then(`Programul a încercat ${tries}.`)
      return card('attention', `Descărcarea de ${when} nu a ajuns la ANAF`, `Verificați conexiunea la internet. ${what}`, { journal: true })
    }
    const stopped = 'Programul sau calculatorul a fost oprit în timpul ei.'
    return card('attention', `Descărcarea de ${when} a fost întreruptă`,
      retry ? `${stopped} Programul o reia ${retry}.` : then(stopped), { journal: true })
  }
  if (run?.status === 'partial') {
    const rest = run.failed_clients > 0
      ? 'Pentru un client descărcarea nu a reușit; se reia la următoarea descărcare.'
      : 'Unele facturi nu s-au putut descărca; se reiau la următoarea descărcare.'
    return card('attention', `Ultima descărcare, ${formatWhen(run.slot, now)}, nu a fost completă`, `${outcome(run)}. ${rest}`, { journal: true })
  }
  const title = next ? `Următoarea descărcare: ${formatNext(status.next_at!, now)}` : 'Descărcarea automată este pornită'
  return run
    ? card('done', title, `Ultima: ${formatWhen(run.slot, now)} · ${outcome(run)}.`, { journal: true })
    : card('done', title, 'Nu a fost făcută încă nicio descărcare automată.')
}

/** The line under "Descărcare automată" in the menu, only when something needs a look. */
export function menuNote(status: ScheduleStatus | undefined): { text: string; tone: 'fresh' | 'attention' } | null {
  if (!status) return null
  if (status.running) return { text: 'Se descarcă acum', tone: 'fresh' }
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
