import { describe, expect, it } from 'vitest'
import { messageForCode } from '../errorMessages'
import type { ScheduleRun, ScheduleStatus } from '../types'
import {
  describePeriod, describeWhen, formProblem, journalAddress, menuNote, onSavedChange, ownSaveArrival, periodSays, pollEvery, runEnded,
  removeTimeName, runningLine, sameSchedule, stateCard,
} from './scheduleTexts'

const NOW = new Date(2026, 10, 16, 9, 0)

const status = (over: Partial<ScheduleStatus> = {}): ScheduleStatus => ({
  enabled: true, days: [0, 1, 2, 3, 4], times: ['08:00'], period: { days: 7 }, next_at: '2026-11-17T08:00:00', running: null, last_run: null,
  clients_on: 3, clients_off: 0, ...over,
})
const run = (over: Partial<ScheduleRun> = {}): ScheduleRun => ({
  slot: '2026-11-16T08:00:00', attempt: 1, started_at: '2026-11-16T08:00:20', finished_at: '2026-11-16T08:01:05',
  status: 'ok', clients: 3, failed_clients: 0, new: 7, review: 2, error: null, retry_at: null, trace: 'c418053e30a7', ...over,
})
const NEXT = 'Următoarea descărcare: mâine, la 08:00'

describe('the days and hours in words', () => {
  it('writes a run of days, every day, a list and a single day', () => {
    expect(describeWhen([0, 1, 2, 3, 4], ['08:00'])).toBe('de luni până vineri, la 08:00')
    expect(describeWhen([0, 1, 2, 3, 4, 5, 6], ['08:00', '14:00'])).toBe('în fiecare zi, la 08:00 și 14:00')
    expect(describeWhen([0, 2, 4], ['08:00', '12:00', '16:00'])).toBe('luni, miercuri și vineri, la 08:00, 12:00 și 16:00')
    expect(describeWhen([5], ['09:30'])).toBe('sâmbătă, la 09:30')
  })
})

describe('what is wrong with the form', () => {
  const usual = { days: 7 }
  const withDates = (enabled: boolean, start: string, end: string) => formProblem(enabled, [0], ['08:00'], { start, end }, NOW)

  it('names the first problem, and none while the schedule is off', () => {
    expect(formProblem(true, [], ['08:00'], usual, NOW)).toBe('Alegeți cel puțin o zi.')
    expect(formProblem(false, [], ['08:00'], usual, NOW)).toBeNull()
    expect(formProblem(true, [0], ['08:00', '08:00'], usual, NOW)).toBe('Aceeași oră apare de două ori.')
    expect(formProblem(true, [0], ['08:00'], usual, NOW)).toBeNull()
  })

  it('checks the hours whatever the switch says; only the days depend on it', () => {
    expect(formProblem(false, [0], ['08:00', '08:00'], usual, NOW)).toBe('Aceeași oră apare de două ori.')
    expect(formProblem(false, [], ['08:00'], usual, NOW)).toBeNull()
  })

  it('wants both days of a period, the first not after the last, whatever the switch says', () => {
    expect(withDates(false, '2026-11-01', '')).toBe('Alegeți amândouă zilele perioadei.')
    expect(withDates(true, '', '2026-11-30')).toBe('Alegeți amândouă zilele perioadei.')
    expect(withDates(false, '2026-11-10', '2026-11-01')).toBe('Prima zi a perioadei este după ultima.')
    expect(withDates(true, '2026-11-01', '2026-11-30')).toBeNull()
    expect(withDates(true, '2026-11-16', '2026-11-16')).toBeNull()
  })

  it('takes only days written as the date fields write them', () => {
    expect(withDates(false, '2026-11-01', '20265-11-30')).toBe('Alegeți amândouă zilele perioadei.')
    expect(withDates(false, '01.11.2026', '2026-11-30')).toBe('Alegeți amândouă zilele perioadei.')
  })

  it('refuses a period ANAF cannot be asked for only while the schedule is on', () => {
    expect(withDates(true, '2026-11-17', '2026-11-30')).toBe('Prima zi a perioadei nu poate fi după azi.')
    expect(withDates(false, '2026-11-17', '2026-11-30')).toBeNull()
    expect(withDates(true, '2026-08-01', '2026-09-16'))
      .toBe('Perioada s-a încheiat de mai mult de 60 de zile, iar ANAF nu mai păstrează facturile din ea.')
    expect(withDates(false, '2026-08-01', '2026-09-16')).toBeNull()
    expect(withDates(true, '2026-08-01', '2026-09-17')).toBeNull() // its last day is the sixtieth back
    expect(withDates(true, '2026-08-01', '2027-01-31')).toBeNull() // began long ago, still running
  })
})

describe('whether two schedules are the same', () => {
  const base = { enabled: true, days: [0, 4], times: ['08:00', '14:00'], period: { days: 7 } }
  const november = { start: '2026-11-01', end: '2026-11-30' }
  it('tells two periods apart', () => {
    expect(sameSchedule({ ...base, period: { days: 3 } }, base)).toBe(false)
    expect(sameSchedule({ ...base, period: november }, { ...base, period: { ...november } })).toBe(true)
    expect(sameSchedule({ ...base, period: november }, { ...base, period: { ...november, end: '2026-11-29' } })).toBe(false)
    expect(sameSchedule({ ...base, period: november }, base)).toBe(false)
  })
  it('ignores the order the days and hours were chosen in', () => {
    expect(sameSchedule({ ...base, days: [4, 0], times: ['14:00', '08:00'] }, base)).toBe(true)
    expect(sameSchedule({ ...base, enabled: false }, base)).toBe(false)
    expect(sameSchedule({ ...base, days: [0] }, { ...base, days: [0, 1] })).toBe(false)
    expect(sameSchedule({ ...base, times: ['08:00'] }, { ...base, times: ['08:30'] })).toBe(false)
  })
})

describe('the state card', () => {
  it('is calm when the last download went well', () => {
    expect(stateCard(status({ last_run: run() }), NOW)).toEqual({
      tone: 'done', title: NEXT, text: 'Ultima: azi, 08:00 · 3 clienți · 7 facturi noi · 2 de verificat.', journal: true, clients: false,
    })
    const none = stateCard(status(), NOW)
    expect(none).toMatchObject({ tone: 'done', title: NEXT, text: 'Nu a fost făcută încă nicio descărcare automată.', journal: false })
    expect(stateCard(status({ last_run: run({ new: 0, review: 0, clients: 1 }) }), NOW).text)
      .toBe('Ultima: azi, 08:00 · un client · nimic nou.')
    // Since the issued invoices are counted apart, only the received ones are "new".
    expect(stateCard(status({ last_run: run({ new: 9, received: 2, issued: 7, review: 0 }) }), NOW).text)
      .toBe('Ultima: azi, 08:00 · 3 clienți · 2 facturi noi · 7 facturi emise.')
    expect(stateCard(status({ last_run: run({ new: 1, received: 0, issued: 1, review: 0 }) }), NOW).text)
      .toBe('Ultima: azi, 08:00 · 3 clienți · o factură emisă.')
  })

  it('says that it is off', () => {
    expect(stateCard(status({ enabled: false, next_at: null, last_run: run({ status: 'failed' }) }), NOW)).toMatchObject({
      tone: 'plain', title: 'Descărcarea automată este oprită',
      text: 'Facturile se descarcă doar când apăsați dumneavoastră „Descarcă facturile”, pe pagina Clienți.',
    })
  })

  it('says that it is downloading', () => {
    const running = { started_at: '2026-11-16T08:00:20', done: 2, total: 3 }
    expect(stateCard(status({ running, last_run: run({ status: 'running' }) }), NOW)).toMatchObject({
      tone: 'fresh', title: 'Se descarcă acum: 2 din 3 clienți',
      text: 'A început azi, 08:00. Pagina se schimbă singură când se termină.',
    })
    expect(stateCard(status({ running: { ...running, total: 0 } }), NOW).title).toBe('Se descarcă acum')
    expect(stateCard(status({ running: { ...running, done: 0, total: 1 } }), NOW).title).toBe('Se descarcă acum')
  })

  it('says that no client is on', () => {
    expect(stateCard(status({ clients_on: 0, clients_off: 2 }), NOW)).toMatchObject({
      tone: 'attention', title: 'Niciun client nu este pornit',
      text: 'Descărcarea automată nu are ce descărca. Porniți clienții din lista de clienți.', clients: true,
    })
  })

  it('says when a run was made, not the moment it was made up for', () => {
    const old = { slot: '2026-11-13T08:00:00', started_at: '2026-11-13T08:00:10' }
    const made = (over: Partial<ScheduleRun>) => stateCard(status({ last_run: run({ ...old, ...over }) }), NOW)
    const login = { code: 'login_needed', message: 'x' }
    const lateRun = { slot: '2026-11-13T08:00:00', started_at: '2026-11-16T08:40:10' }
    expect(stateCard(status({ last_run: run(lateRun) }), NOW).text).toBe('Ultima: azi, 08:40 · 3 clienți · 7 facturi noi · 2 de verificat.')
    expect(stateCard(status({ last_run: run({ ...lateRun, status: 'failed', error: login }) }), NOW).title)
      .toBe('Descărcarea de azi, 08:40 nu a reușit')
    expect(made({ status: 'failed', error: login }).title).toBe('Descărcarea din 13.11.2026, 08:00 nu a reușit')
    expect(made({ status: 'unreachable' }).title).toBe('Descărcarea din 13.11.2026, 08:00 nu a ajuns la ANAF')
    expect(made({ status: 'interrupted' }).title).toBe('Descărcarea din 13.11.2026, 08:00 a fost întreruptă')
    expect(made({ status: 'partial', failed_clients: 1 }).title).toBe('Ultima descărcare, 13.11.2026, 08:00, nu a fost completă')
  })

  it('sends her to the journal when the cause has no sentence of its own', () => {
    const card = stateCard(status({ last_run: run({ status: 'failed', error: { code: 'internal_error', message: 'x' } }) }), NOW)
    expect(card.text).toBe(`A apărut o problemă în program. Detaliile sunt în jurnal. ${NEXT}.`)
    expect(card.journal).toBe(true)
    expect(stateCard(status({ last_run: run({ status: 'failed', error: { code: 'never_heard_of', message: 'x' } }) }), NOW).text)
      .toBe(`A apărut o problemă în program. Detaliile sunt în jurnal. ${NEXT}.`)
  })

  it('says why a download failed', () => {
    const failed = stateCard(status({ last_run: run({ status: 'failed', error: { code: 'login_needed', message: 'x' } }) }), NOW)
    expect(failed).toMatchObject({ tone: 'attention', title: 'Descărcarea de azi, 08:00 nu a reușit' })
    expect(failed.text).toBe(`${messageForCode('login_needed')} ${NEXT}.`)
    expect(failed.journal).toBe(true)
  })

  it('says when ANAF could not be reached', () => {
    const card = (over: Partial<ScheduleRun>) => stateCard(status({ last_run: run({ status: 'unreachable', ...over }) }), NOW)
    expect(card({ retry_at: '2026-11-16T08:15:20' })).toMatchObject({
      tone: 'attention', title: 'Descărcarea de azi, 08:00 nu a ajuns la ANAF',
      text: 'Verificați conexiunea la internet. Programul mai încearcă azi, la 08:15 (încercarea 2 din 4).',
    })
    expect(card({ attempt: 4 }).text).toBe(`Verificați conexiunea la internet. Programul a încercat de 4 ori. ${NEXT}.`)
    expect(card({}).journal).toBe(true)
    expect(card({ attempt: 1 }).text).toBe(`Verificați conexiunea la internet. Programul a încercat o dată. ${NEXT}.`)
  })

  it('says that a download was interrupted', () => {
    const card = (over: Partial<ScheduleRun>) => stateCard(status({ last_run: run({ status: 'interrupted', ...over }) }), NOW)
    expect(card({ retry_at: '2026-11-16T08:15:20' })).toMatchObject({
      title: 'Descărcarea de azi, 08:00 a fost întreruptă',
      text: 'Programul sau calculatorul a fost oprit în timpul ei. Programul o reia azi, la 08:15.',
    })
    expect(card({ attempt: 4 }).text).toBe(`Programul sau calculatorul a fost oprit în timpul ei. ${NEXT}.`)
    expect(card({}).journal).toBe(true)
  })

  it('says that a download was not complete', () => {
    expect(stateCard(status({ last_run: run({ status: 'partial', failed_clients: 1 }) }), NOW)).toMatchObject({
      tone: 'attention', title: 'Ultima descărcare, azi, 08:00, nu a fost completă', journal: true,
      text: '3 clienți · 7 facturi noi · 2 de verificat. Pentru un client descărcarea nu a reușit; se reia la următoarea descărcare.',
    })
    expect(stateCard(status({ last_run: run({ status: 'partial', failed_clients: 3 }) }), NOW).text)
      .toBe('3 clienți · 7 facturi noi · 2 de verificat. Pentru 3 clienți descărcarea nu a reușit; se reia la următoarea descărcare.')
    expect(stateCard(status({ last_run: run({ status: 'partial', failed_clients: 0 }) }), NOW).text)
      .toBe('3 clienți · 7 facturi noi · 2 de verificat. Unele facturi nu s-au putut descărca; se reiau la următoarea descărcare.')
  })
})

describe('the note in the menu', () => {
  it('shows only what needs a look', () => {
    expect(menuNote(undefined)).toBeNull()
    expect(menuNote(status({ last_run: run() }))).toBeNull()
    expect(menuNote(status({ running: { started_at: '2026-11-16T08:00:20', done: 0, total: 3 } })))
      .toEqual({ text: 'Se descarcă acum', tone: 'fresh' })
    for (const bad of ['failed', 'unreachable', 'interrupted'] as const) {
      expect(menuNote(status({ last_run: run({ status: bad }) }))).toEqual({ text: 'Ultima nu a reușit', tone: 'attention' })
    }
    expect(menuNote(status({ enabled: false, last_run: run({ status: 'failed' }) }))).toBeNull()
  })
})

describe('how often the page asks', () => {
  it('asks fast while downloading, slowly while waiting, never while off', () => {
    const running = { started_at: '2026-11-16T08:00:20', done: 0, total: 3 }
    expect(pollEvery(undefined)).toBe(false)
    expect(pollEvery(status({ enabled: false }))).toBe(false)
    expect(pollEvery(status())).toBe(30000)
    expect(pollEvery(status({ running }))).toBe(3000)
    expect(pollEvery(status({ enabled: false, running }))).toBe(3000)
  })
})

describe('what the form does when the saved schedule is not the one it follows', () => {
  const a = { enabled: true, days: [0], times: ['08:00'], period: { days: 7 } }
  const b = { enabled: true, days: [0, 1], times: ['08:00'], period: { days: 7 } }
  const c = { enabled: false, days: [2], times: ['09:00'], period: { days: 7 } }
  it('follows when nothing would be lost, shows a notice when edits would', () => {
    expect(onSavedChange(c, a, { ...a, days: [0] })).toBe('nothing')
    expect(onSavedChange(a, a, b)).toBe('follow')
    expect(onSavedChange(b, a, b)).toBe('follow')
    expect(onSavedChange(c, a, b)).toBe('notice')
  })
})

describe('after her own save', () => {
  const a = { enabled: true, days: [0], times: ['08:00'], period: { days: 7 } }
  const b = { enabled: true, days: [0, 1], times: ['08:00'], period: { days: 7 } }
  const c = { enabled: false, days: [2], times: ['09:00'], period: { days: 7 } }
  it('tells whether the saved schedule became her answer, is still the old one, or was overtaken', () => {
    expect(ownSaveArrival(b, b, a)).toBe('arrived')
    expect(ownSaveArrival(a, a, a)).toBe('arrived')
    expect(ownSaveArrival(a, b, a)).toBe('waiting')
    expect(ownSaveArrival(c, b, a)).toBe('overtaken')
  })
})

describe('the first line of the notice on the client list', () => {
  it('counts the clients only when there is more than one', () => {
    expect(runningLine(2, 3)).toBe('Programul descarcă acum facturile, singur: 2 din 3 clienți.')
    expect(runningLine(0, 1)).toBe('Programul descarcă acum facturile, singur.')
    expect(runningLine(0, 0)).toBe('Programul descarcă acum facturile, singur.')
  })
})

describe('whether an automatic download ended that the lists have not seen', () => {
  const running = { started_at: '2026-11-16T08:00:20', done: 1, total: 3 }
  const finished = (at: string | null, over: Partial<ScheduleStatus> = {}) =>
    status({ last_run: run({ finished_at: at }), ...over })
  it('is false without two reads', () => {
    expect(runEnded(undefined, status())).toBe(false)
    expect(runEnded(status(), undefined)).toBe(false)
  })
  it('is true when a run in progress is gone, or a run ended since the last read', () => {
    expect(runEnded(status({ running }), status())).toBe(true)
    expect(runEnded(finished('2026-11-15T08:01:00'), finished('2026-11-16T08:01:05'))).toBe(true)
    expect(runEnded(status(), finished('2026-11-16T08:01:05'))).toBe(true)
  })
  it('is false when nothing ended or a run is still going', () => {
    expect(runEnded(finished('2026-11-16T08:01:05'), finished('2026-11-16T08:01:05'))).toBe(false)
    expect(runEnded(finished('2026-11-15T08:01:00'), finished('2026-11-15T08:01:00', { running }))).toBe(false)
    expect(runEnded(status(), status())).toBe(false)
  })
})

describe('the remove button of a time', () => {
  it('is named by its time', () => {
    expect(removeTimeName('14:00')).toBe('Scoate ora 14:00')
  })
})

describe('the journal address of a run', () => {
  it('is the whole journal without a trace, and the run\'s own lines with one', () => {
    expect(journalAddress(null)).toBe('/jurnal')
    expect(journalAddress(undefined)).toBe('/jurnal')
    expect(journalAddress('')).toBe('/jurnal')
    expect(journalAddress('c418053e30a7')).toBe('/jurnal?operatiune=c418053e30a7')
  })
})

describe('the period in words', () => {
  it('says which invoices a download brings', () => {
    expect(describePeriod({ days: 7 })).toBe('facturile sosite în ultimele 7 zile')
    expect(describePeriod({ days: 1 })).toBe('facturile sosite în ultima zi')
    expect(describePeriod({ days: 30 })).toBe('facturile sosite în ultimele 30 de zile')
    expect(describePeriod({ start: '2026-11-01', end: '2026-11-30' })).toBe('facturile sosite în perioada 01.11.2026 – 30.11.2026')
    expect(describePeriod({ start: '2026-11-16', end: '2026-11-16' })).toBe('facturile sosite pe 16.11.2026')
  })

  it('explains under the fields what the choice means', () => {
    expect(periodSays({ days: 3 })).toBe(
      'La fiecare descărcare, programul aduce facturile sosite în ultimele 3 zile. Dacă a stat oprit mai mult de atât, merge înapoi până la ultima descărcare completă.',
    )
    expect(periodSays({ start: '2026-11-01', end: '2026-11-30' })).toBe(
      'La fiecare descărcare, programul aduce facturile sosite în perioada 01.11.2026 – 30.11.2026. Perioada rămâne aceeași: după 30.11.2026 nu mai vin facturi noi până nu alegeți altă perioadă.',
    )
  })

  it('asks for the two days while they are not both there, in their order', () => {
    expect(periodSays({ start: '2026-11-01', end: '' })).toBe('Alegeți prima și ultima zi a perioadei.')
    expect(periodSays({ start: '', end: '' })).toBe('Alegeți prima și ultima zi a perioadei.')
    expect(periodSays({ start: '2026-11-30', end: '2026-11-01' })).toBe('Alegeți prima și ultima zi a perioadei.')
    expect(periodSays({ start: '2026-11-01', end: '20265-11-30' })).toBe('Alegeți prima și ultima zi a perioadei.')
  })
})

describe('a period whose last day has passed', () => {
  const ended = { start: '2026-11-01', end: '2026-11-15' }
  const lastDayToday = { start: '2026-11-01', end: '2026-11-16' }

  const refused = run({ status: 'failed', error: { code: 'invalid_input', message: 'x' } })
  const noLogin = run({ status: 'failed', error: { code: 'login_needed', message: 'x' } })

  it('is what the state card says after a download that went well, with the next one and the way to the journal', () => {
    expect(stateCard(status({ period: ended, last_run: run() }), NOW)).toEqual({
      tone: 'attention', title: 'Perioada aleasă s-a încheiat pe 15.11.2026',
      text: 'Descărcarea automată mai aduce doar facturile din perioada aceasta. Pentru cele sosite după 15.11.2026, alegeți mai jos altă perioadă. Următoarea descărcare: mâine, la 08:00.',
      journal: true, clients: false,
    })
    expect(stateCard(status({ period: ended }), NOW).journal).toBe(false)
    expect(stateCard(status({ period: ended, last_run: run({ status: 'partial', failed_clients: 1 }) }), NOW).title)
      .toBe('Perioada aleasă s-a încheiat pe 15.11.2026')
  })

  it('gives way to a download that did not work for another reason', () => {
    expect(stateCard(status({ period: ended, last_run: noLogin }), NOW).title).toBe('Descărcarea de azi, 08:00 nu a reușit')
    expect(stateCard(status({ period: ended, last_run: run({ status: 'unreachable' }) }), NOW).title)
      .toBe('Descărcarea de azi, 08:00 nu a ajuns la ANAF')
    expect(stateCard(status({ period: ended, last_run: run({ status: 'interrupted' }) }), NOW).title)
      .toBe('Descărcarea de azi, 08:00 a fost întreruptă')
    expect(menuNote(status({ period: ended, last_run: noLogin }), NOW)).toEqual({ text: 'Ultima nu a reușit', tone: 'attention' })
  })

  it('is still said when the download was refused because of the period itself', () => {
    expect(stateCard(status({ period: ended, last_run: refused }), NOW).title).toBe('Perioada aleasă s-a încheiat pe 15.11.2026')
    expect(menuNote(status({ period: ended, last_run: refused }), NOW)).toEqual({ text: 'Perioada s-a încheiat', tone: 'attention' })
  })

  it('says that ANAF has nothing left of a period that ended over 60 days ago', () => {
    expect(stateCard(status({ period: { start: '2026-08-01', end: '2026-09-16' } }), NOW).text)
      .toBe('ANAF păstrează facturile doar 60 de zile, așa că programul nu mai are ce aduce din perioada aceasta. Alegeți mai jos altă perioadă.')
    expect(stateCard(status({ period: { start: '2026-08-01', end: '2026-09-17' } }), NOW).text)
      .toBe('Descărcarea automată mai aduce doar facturile din perioada aceasta. Pentru cele sosite după 17.09.2026, alegeți mai jos altă perioadă. Următoarea descărcare: mâine, la 08:00.')
  })

  it('is not said on the last day, while the schedule is off, or while a download is going', () => {
    expect(stateCard(status({ period: lastDayToday }), NOW).title).toBe(NEXT)
    expect(stateCard(status({ enabled: false, next_at: null, period: ended }), NOW).title).toBe('Descărcarea automată este oprită')
    const running = { started_at: '2026-11-16T08:00:20', done: 0, total: 1 }
    expect(stateCard(status({ period: ended, running }), NOW).title).toBe('Se descarcă acum')
  })

  it('is what the menu says, unless a download is going', () => {
    expect(menuNote(status({ period: ended, last_run: run() }), NOW)).toEqual({ text: 'Perioada s-a încheiat', tone: 'attention' })
    expect(menuNote(status({ period: ended }), NOW)).toEqual({ text: 'Perioada s-a încheiat', tone: 'attention' })
    expect(menuNote(status({ period: lastDayToday }), NOW)).toBeNull()
    expect(menuNote(status({ enabled: false, period: ended }), NOW)).toBeNull()
    expect(menuNote(status({ period: ended, running: { started_at: '2026-11-16T08:00:20', done: 0, total: 1 } }), NOW))
      .toEqual({ text: 'Se descarcă acum', tone: 'fresh' })
  })
})
