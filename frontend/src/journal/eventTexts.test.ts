import { describe, expect, it } from 'vitest'
import { areaName, describeEvent, formatDuration } from './eventTexts'
import type { JournalLine } from '../types'

const line = (event: string | null, data: Record<string, unknown> = {}, extra: Partial<JournalLine> = {}): JournalLine => ({
  id: 1, at: '2026-11-14T09:31:07+02:00', level: 'info', area: 'sync', event, message: 'In English.', data,
  trace: null, duration_ms: null, ...extra,
})

describe('a line of the journal, in Romanian', () => {
  it('tells how a download ended', () => {
    expect(describeEvent(line('sync.finished', { client: 'Alfa Construct SRL', cui: '12345674', new: 3, failed: 0 })))
      .toBe('Descărcarea pentru Alfa Construct SRL s-a terminat: 3 facturi noi, niciuna nereușită.')
    expect(describeEvent(line('sync.finished', { cui: '12345674', new: 0, failed: 2 })))
      .toBe('Descărcarea pentru CUI 12345674 s-a terminat: nicio factură nouă, 2 nereușite.')
    expect(describeEvent(line('sync.finished', { cui: '12345674', new: 1, failed: 1 })))
      .toBe('Descărcarea pentru CUI 12345674 s-a terminat: o factură nouă, una nereușită.')
  })

  it('tells who chose an account', () => {
    expect(describeEvent(line('account.by_rule', { invoice_number: 'FV-1042', cont: '6022' })))
      .toBe('Factura FV-1042 a primit contul 6022, după o regulă a dumneavoastră.')
    expect(describeEvent(line('account.by_jev', { invoice_number: 'MC 5521', cont: '302', confidence: 0.93 })))
      .toBe('Factura MC 5521 a primit contul 302, ales de Jev (sigur 93%).')
    expect(describeEvent(line('account.to_review', { invoice_number: 'MC 5521' })))
      .toBe('Factura MC 5521 este de verificat: trebuie să îi alegeți contul.')
  })

  it('tells when a client was switched off or on', () => {
    expect(describeEvent(line('client.switched', { client: 'Alfa SRL', cui: '12345674', enabled: false })))
      .toBe('Clientul Alfa SRL a fost oprit: facturile lui nu se mai descarcă.')
    expect(describeEvent(line('client.switched', { client: 'Alfa SRL', cui: '12345674', enabled: true })))
      .toBe('Clientul Alfa SRL a fost pornit: facturile lui se descarcă din nou.')
  })

  it('tells what a trial invoice got', () => {
    expect(describeEvent(line('rule.tested', { decided_by: 'jev', cont: '302', asked_jev: true, cost_usd: 0.00002 })))
      .toBe('A fost încercată o factură de probă: contul 302, ales de Jev.')
    expect(describeEvent(line('rule.tested', { decided_by: 'rule', cont: '6022', asked_jev: false, cost_usd: null })))
      .toBe('A fost încercată o factură de probă: contul 6022, ales de o regulă.')
    expect(describeEvent(line('rule.tested', { decided_by: 'nobody', cont: null, asked_jev: true, cost_usd: 0.00002 })))
      .toBe('A fost încercată o factură de probă: nu a primit niciun cont.')
  })

  it('never shows which key was changed as anything but its name', () => {
    expect(describeEvent(line('settings.secret_changed', { name: 'openrouter_api_key' })))
      .toBe('A fost schimbată o cheie: cheia OpenRouter.')
  })

  it('tells what happened to a copy without guessing why one failed', () => {
    expect(describeEvent(line('backup.made', { kind: 'manual' }))).toBe('A fost făcută o copie de siguranță, la cererea dumneavoastră.')
    expect(describeEvent(line('backup.made', { kind: 'auto' }))).toBe('A fost făcută o copie de siguranță, automat.')
    expect(describeEvent(line('backup.made', { kind: 'before-restore' })))
      .toBe('A fost făcută o copie de siguranță, înaintea restaurării.')
    expect(describeEvent(line('backup.failed', { folder: 'E:\\Copii', folder_found: false })))
      .toBe('Copia de siguranță nu a reușit: folderul E:\\Copii nu a fost găsit.')
    expect(describeEvent(line('backup.failed', { folder: 'E:\\Copii', folder_found: true, error: 'No space left on device' })))
      .toBe('Copia de siguranță în folderul E:\\Copii nu a reușit.')
    expect(describeEvent(line('restore.not_restarted')))
      .toBe('După restaurare programul nu a pornit singur. Faceți dublu clic pe „AutoSaga” de pe Desktop.')
  })

  it('makes "imported" agree with one invoice and with several', () => {
    expect(describeEvent(line('invoices.marked_imported', { invoices: 1 }))).toBe('O factură a fost bifată ca importată în SAGA.')
    expect(describeEvent(line('invoices.marked_imported', { invoices: 3 }))).toBe('3 facturi au fost bifate ca importate în SAGA.')
    expect(describeEvent(line('invoices.unmarked', { invoices: 1 }))).toBe('O factură nu mai este bifată ca importată în SAGA.')
    expect(describeEvent(line('invoices.unmarked', { invoices: 25 }))).toBe('25 de facturi nu mai sunt bifate ca importate în SAGA.')
  })

  it('says Windows was asked for the certificate', () => {
    expect(describeEvent(line('anaf.certificate_asked', { outcome: 'answered', tries: 2, opened_first: false }, { area: 'anaf' })))
      .toBe('Programul a cerut certificatul de la Windows.')
  })

  it('says for how many days back a download looks', () => {
    expect(describeEvent(line('sync.started', { client: 'Alfa Construct SRL', window_days: 60 })))
      .toBe('A început descărcarea pentru Alfa Construct SRL, pentru ultimele 60 de zile.')
    expect(describeEvent(line('sync.started', { cui: '12345674', window_days: 5 })))
      .toBe('A început descărcarea pentru CUI 12345674, pentru ultimele 5 zile.')
    expect(describeEvent(line('sync.started', { cui: '12345674', window_days: 1 })))
      .toBe('A început descărcarea pentru CUI 12345674, pentru ultima zi.')
  })

  it('says a cost is unknown instead of showing a number that is not one', () => {
    expect(describeEvent(line('jev.answered', {}))).toBe('Jev a răspuns. Cost: necunoscut.')
    expect(describeEvent(line('jev.answered', { cost_usd: null }))).toBe('Jev a răspuns. Cost: necunoscut.')
    expect(describeEvent(line('jev.answered', { cost_usd: 0.42 }, { duration_ms: 820 })).replace(/\s/g, ' '))
      .toBe('Jev a răspuns în 0,8 s. Cost: 0,42 $.')
  })

  it('counts imported clients without making the words agree with the numbers', () => {
    expect(describeEvent(line('clients.imported', { file: 'clienti.xlsx', added: 1, updated: 0, rejected: 1 })))
      .toBe('Clienți importați din clienti.xlsx: adăugați: 1, modificați: 0, respinși: 1.')
  })

  it('tells where the earlier database is when it could not be copied before a restore', () => {
    expect(describeEvent(line('restore.kept_aside', { kept_as: 'efactura.before-restore.db', error: 'No space left on device' })))
      .toBe('Baza de date de dinainte nu a putut fi copiată în folderul copiilor; a fost păstrată lângă program, în fișierul efactura.before-restore.db.')
  })

  it('tells what to do when the program did not start again after an update', () => {
    expect(describeEvent(line('update.not_restarted', { error: 'spawn failed' })))
      .toBe('După actualizare programul nu a pornit singur. Faceți dublu clic pe „AutoSaga” de pe Desktop.')
  })

  it('keeps the English line for what it does not know', () => {
    expect(describeEvent(line('something.new'))).toBe('In English.')
    expect(describeEvent(line(null))).toBe('In English.')
  })

  it('says how long a step took', () => {
    expect(formatDuration(820)).toBe('0,8 s')
    expect(formatDuration(45)).toBe('45 ms')
    expect(formatDuration(6100)).toBe('6,1 s')
    expect(formatDuration(null)).toBe('')
  })

  it('names the areas', () => {
    expect(areaName('sync')).toBe('Descărcări')
    expect(areaName('something')).toBe('something')
  })
  it('tells about the automatic download', () => {
    const say = (event: string, data: Record<string, unknown>) => describeEvent(line(event, data))
    expect(say('schedule.saved', { enabled: true, days: [0, 1, 2, 3, 4], times: ['08:00', '14:00'] }))
      .toBe('Descărcarea automată a fost pornită: de luni până vineri, la 08:00 și 14:00.')
    expect(say('schedule.saved', { enabled: false, days: [0], times: ['08:00'] })).toBe('Descărcarea automată a fost oprită.')
    expect(say('schedule.saved', { enabled: true, days: [0, 1, 2, 3, 4], times: ['08:00'], period: { days: 3 } }))
      .toBe('Descărcarea automată a fost pornită: de luni până vineri, la 08:00, pentru facturile sosite în ultimele 3 zile.')
    expect(say('schedule.saved', { enabled: true, days: [5], times: ['09:30'], period: { start: '2026-11-01', end: '2026-11-30' } }))
      .toBe('Descărcarea automată a fost pornită: sâmbătă, la 09:30, pentru facturile sosite în perioada 01.11.2026 – 30.11.2026.')
    expect(say('sync.auto_finished', { status: 'failed', error: 'invalid_input' }))
      .toBe('Descărcarea automată nu a reușit: ANAF nu mai păstrează facturile din perioada aleasă.')
    expect(say('sync.auto_started', { attempt: 1 })).toBe('Descărcarea automată a început.')
    expect(say('sync.auto_started', { attempt: 2 })).toBe('Descărcarea automată a început. Este încercarea 2 din 4.')
    expect(say('sync.auto_finished', { status: 'ok', new: 7, review: 2 }))
      .toBe('Descărcarea automată s-a terminat: 7 facturi noi, 2 de verificat.')
    expect(say('sync.auto_finished', { status: 'ok', new: 0, review: 0 })).toBe('Descărcarea automată s-a terminat: nimic nou.')
    expect(say('sync.auto_finished', { status: 'partial', new: 1, review: 0 }))
      .toBe('Descărcarea automată s-a terminat: o factură nouă. Nu a fost completă; se reia la următoarea descărcare.')
    expect(say('sync.auto_finished', { status: 'failed', error: 'login_needed' }))
      .toBe('Descărcarea automată nu a reușit: trebuie să vă conectați din nou la ANAF.')
    expect(say('sync.auto_finished', { status: 'failed', error: 'anaf_error' }))
      .toBe('Descărcarea automată nu a reușit: ANAF a răspuns cu o eroare.')
    expect(say('sync.auto_finished', { status: 'failed', error: 'internal_error' })).toBe('Descărcarea automată nu a reușit.')
    expect(say('sync.auto_finished', { status: 'unreachable', attempt: 1 }))
      .toBe('Descărcarea automată nu a ajuns la ANAF. Programul mai încearcă peste un sfert de oră.')
    expect(say('sync.record_unsaved', {})).toBe('Descărcarea automată s-a terminat, dar rezultatul ei nu a putut fi salvat.')
    expect(say('sync.auto_finished', { status: 'unreachable', attempt: 4 }))
      .toBe('Descărcarea automată nu a ajuns la ANAF. A fost ultima încercare pentru această oră.')
  })
})
