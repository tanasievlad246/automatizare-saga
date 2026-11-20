import { describe, expect, it } from 'vitest'
import type { JournalLine, TechnicalRecord } from '../types'
import {
  bodyNote, clockFine, countsText, formatBytes, operationSummary, readableBody, recordLevelName, shortAddress,
  statusLook, timeline,
} from './technical'

const line = (id: number, at: string): JournalLine => ({
  id, at, level: 'info', area: 'sync', event: 'sync.started', message: 'In English.', data: {}, trace: 't1', duration_ms: null,
})
const call = (id: number, at: string, extra: Partial<TechnicalRecord> = {}): TechnicalRecord => ({
  id, at, trace: 't1', kind: 'http', level: 'info', summary: 'GET …', method: 'GET',
  url: 'https://api.anaf.ro/prod/FCTEL/rest/descarcare?id=1', status: 200, duration_ms: 120, service: 'anaf', ...extra,
})
const record = (id: number, at: string): TechnicalRecord => ({
  id, at, trace: 't1', kind: 'log', level: 'debug', summary: 'Window …', logger: 'efactura.service',
  where: 'service.py:441', function: 'sync', has_exception: false,
})

describe('one operation, step by step, with its requests', () => {
  it('puts each request and program record where it happened among the steps', () => {
    const steps = [line(1, '2026-11-20T09:30:58.102000+02:00'), line(2, '2026-11-20T09:31:07.412000+02:00')]
    const records = [call(10, '2026-11-20T09:30:58.421000+02:00'), record(11, '2026-11-20T09:30:58.104000+02:00')]

    expect(timeline(steps, true, records, true).map((item) => `${item.kind}:${item.kind === 'line' ? item.line.id : item.record.id}`))
      .toEqual(['line:1', 'record:11', 'record:10', 'line:2'])
  })

  it('puts a record written at the same moment as a step before it: the step tells of it', () => {
    const at = '2026-11-20T09:30:58.421000+02:00'
    expect(timeline([line(1, at)], true, [call(10, at)], true).map((item) => item.kind)).toEqual(['record', 'line'])
  })

  it('shows nothing from before what both lists have read, so a gap is not mistaken for silence', () => {
    const steps = [line(1, '2026-11-20T09:00:00.000000+02:00'), line(2, '2026-11-20T09:10:00.000000+02:00')]
    const records = [call(10, '2026-11-20T09:05:00.000000+02:00'), call(11, '2026-11-20T09:12:00.000000+02:00')]

    // Older records wait to be read: the steps before the oldest one read are left out for now.
    expect(timeline(steps, true, records, false).map((item) => item.kind === 'line' ? item.line.id : item.record.id))
      .toEqual([10, 2, 11])
    // Older steps wait to be read: the records before the oldest step read are left out for now.
    expect(timeline(steps, false, records, true).map((item) => item.kind === 'line' ? item.line.id : item.record.id))
      .toEqual([1, 10, 2, 11])
    expect(timeline(steps.slice(1), false, records, true).map((item) => item.kind === 'line' ? item.line.id : item.record.id))
      .toEqual([2, 11])
  })
})

describe('a request in words', () => {
  it('tells by its look an answer that worked from one that was limited or failed', () => {
    expect(statusLook(call(1, '', { status: 200 }))).toBe('ok')
    expect(statusLook(call(1, '', { status: 302 }))).toBe('ok')
    expect(statusLook(call(1, '', { status: 429 }))).toBe('limited')
    expect(statusLook(call(1, '', { status: 503 }))).toBe('failed')
    expect(statusLook(call(1, '', { status: null }))).toBe('failed')
  })

  it('shortens an address to what tells it apart', () => {
    expect(shortAddress('https://api.anaf.ro/prod/FCTEL/rest/descarcare?id=1')).toBe('api.anaf.ro/prod/FCTEL/rest/descarcare?id=1')
    expect(shortAddress('http://127.0.0.1/x')).toBe('127.0.0.1/x')
  })

  it('writes sizes as a programmer reads them', () => {
    expect(formatBytes(312)).toBe('312 B')
    expect(formatBytes(1214)).toBe('1,2 kB')
    expect(formatBytes(151_552)).toBe('148 kB')
    expect(formatBytes(2_500_000)).toBe('2,4 MB')
  })

  it('shows the time down to the thousandth of a second', () => {
    expect(clockFine('2026-11-20T09:30:58.102345+02:00')).toBe('09:30:58,102')
    expect(clockFine('2026-11-20T09:30:58+02:00')).toBe('09:30:58,000')
  })

  it('names the level of a program record in Romanian', () => {
    expect(recordLevelName('debug')).toBe('Depanare')
    expect(recordLevelName('warning')).toBe('Atenție')
  })
})

describe('what was sent and what came back', () => {
  it('lays JSON and XML out to be read, and leaves anything else as it came', () => {
    expect(readableBody({ format: 'json', type: 'application/json', bytes: 9, text: '{"a":[1,2]}' })).toBe('{\n  "a": [\n    1,\n    2\n  ]\n}')
    expect(readableBody({ format: 'xml', type: 'application/xml', bytes: 9, text: '<a><b>1</b></a>' })).toBe('<a>\n  <b>1</b>\n</a>')
    expect(readableBody({ format: 'form', type: null, bytes: 9, text: 'a=1&b=[hidden]' })).toBe('a=1\nb=[hidden]')
    // Cut short, it is no longer JSON: it is shown as it was kept.
    expect(readableBody({ format: 'json', type: 'application/json', bytes: 900, text: '{"a":[1,', cut: true })).toBe('{"a":[1,')
  })

  it('says what a body was when it is not kept', () => {
    expect(bodyNote({ empty: true })).toBe('Fără conținut.')
    expect(bodyNote({ binary: true, type: 'application/zip', bytes: 4915 })).toBe('Conținut binar (application/zip, 4,8 kB): nu se păstrează, doar mărimea lui.')
    expect(bodyNote({ binary: true, type: null, bytes: 4915 })).toBe('Conținut binar (4,8 kB): nu se păstrează, doar mărimea lui.')
    expect(bodyNote({ too_large: true, type: 'application/json', bytes: 2_500_000 })).toBe('Conținut prea mare (2,4 MB): nu se păstrează.')
    expect(bodyNote({ format: 'json', type: 'application/json', bytes: 1214, text: '{}' })).toBe('JSON, 1,2 kB')
    expect(bodyNote({ format: 'text', type: 'text/plain', bytes: 151_552, text: 'x'.repeat(32768), cut: true }))
      .toBe('Text, 148 kB. Tăiat: s-au păstrat primele 32 kB.')
  })
})

describe('how much an operation holds', () => {
  it('counts its requests and program records for the link to it', () => {
    expect(countsText({ http: 4, problems: 1, log: 11 })).toBe('4 cereri, una cu eroare, 11 rânduri din program')
    expect(countsText({ http: 1, problems: 0, log: 1 })).toBe('o cerere, un rând din program')
    expect(countsText({ http: 0, problems: 0, log: 25 })).toBe('25 de rânduri din program')
    expect(countsText(undefined)).toBe('')
  })

  it('sums the operation up: to whom it spoke, what went wrong, from when to when', () => {
    const records = [
      call(1, '2026-11-20T09:30:58.421000+02:00'),
      call(2, '2026-11-20T09:31:02.031000+02:00', { status: 429, level: 'warning' }),
      call(3, '2026-11-20T09:31:04.211000+02:00', { service: 'jev', method: 'POST' }),
      call(4, '2026-11-20T09:30:57.000000+02:00', { service: 'anaf_login', method: 'POST' }),
      record(5, '2026-11-20T09:31:07.398000+02:00'),
    ]
    expect(operationSummary(records)).toEqual({
      requests: '4 cereri: 3 către ANAF, una către Jev', problems: 'una cu eroare', records: 'un rând din program',
      from: '09:30:57', to: '09:31:07',
    })
    expect(operationSummary([])).toBeNull()
  })
})
