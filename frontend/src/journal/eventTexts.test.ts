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

  it('tells the received invoices of a download from the ones the client issued', () => {
    expect(describeEvent(line('sync.finished', { cui: '12345674', new: 8, received: 3, issued: 5, failed: 0 })))
      .toBe('Descărcarea pentru CUI 12345674 s-a terminat: 3 facturi primite noi, 5 emise noi, niciuna nereușită.')
    expect(describeEvent(line('sync.finished', { cui: '12345674', new: 1, received: 0, issued: 1, failed: 0 })))
      .toBe('Descărcarea pentru CUI 12345674 s-a terminat: nicio factură primită, o emisă nouă, niciuna nereușită.')
    expect(describeEvent(line('sync.finished', { cui: '12345674', new: 2, received: 2, issued: 0, failed: 0 })))
      .toBe('Descărcarea pentru CUI 12345674 s-a terminat: 2 facturi noi, niciuna nereușită.')
  })

  it('tells how a client\'s invoices to check were classified again', () => {
    const again = { client: 'Alfa Construct SRL', cui: '12345674', total: 7, classified: 5, review: 2, waiting: 0, jev_asked: true }
    expect(describeEvent(line('classification.again', again)))
      .toBe('Facturile de verificat ale clientului Alfa Construct SRL au fost clasificate din nou: 7 facturi, 5 au primit cont, 2 rămân de verificat.')
    expect(describeEvent(line('classification.again', { ...again, total: 1, classified: 0, review: 0, waiting: 1, jev_asked: false })))
      .toBe('Facturile de verificat ale clientului Alfa Construct SRL au fost clasificate din nou, doar după reguli: o factură, niciuna nu a primit cont, una așteaptă încă răspunsul lui Jev.')
    expect(describeEvent(line('classification.again', { ...again, total: 65, classified: 25, review: 20, waiting: 20 })))
      .toBe('Facturile de verificat ale clientului Alfa Construct SRL au fost clasificate din nou: 65 de facturi, 25 au primit cont, 20 rămân de verificat, 20 așteaptă încă răspunsul lui Jev.')
    expect(describeEvent(line('classification.again', { ...again, classified: 0, review: 7, jev_stopped: true })))
      .toBe('Facturile de verificat ale clientului Alfa Construct SRL au fost clasificate din nou: 7 facturi, niciuna nu a primit cont, 7 rămân de verificat. Jev nu a mai răspuns.')
  })

  it('tells who chose an account', () => {
    expect(describeEvent(line('account.by_rule', { invoice_number: 'FV-1042', cont: '6022' })))
      .toBe('Factura FV-1042 a primit contul 6022, după o regulă a dumneavoastră.')
    expect(describeEvent(line('account.by_jev', { invoice_number: 'MC 5521', cont: '302', confidence: 0.93 })))
      .toBe('Factura MC 5521 a primit contul 302, ales de Jev (sigur 93%).')
    expect(describeEvent(line('account.to_review', { invoice_number: 'MC 5521' })))
      .toBe('Factura MC 5521 este de verificat: trebuie să îi alegeți contul.')
  })

  it('tells how an invoice decided line by line got its accounts, in one line', () => {
    expect(describeEvent(line('account.by_lines', {
      invoice_number: 'CO 1879', lines: 3, by_rules: 2, by_jev: 1, by_person: 0, following: 0, accounts: ['605', '6581'],
    }))).toBe('Factura CO 1879 are un cont pe fiecare linie: 2 linii după reguli, o linie de la Jev. Conturile: 605, 6581.')
    expect(describeEvent(line('account.by_lines', {
      invoice_number: 'PS 7', lines: 23, by_rules: 0, by_jev: 0, by_person: 22, following: 1, accounts: ['6024'],
    }))).toBe('Factura PS 7 are un cont pe fiecare linie: 22 de linii alese de dumneavoastră, o linie cu contul liniei celei mai mari. Contul: 6024.')
    expect(describeEvent(line('account.by_lines', {
      invoice_number: 'BE 418', lines: 3, by_rules: 1, by_jev: 0, by_person: 0, following: 0, as_invoice: 2, accounts: ['302'],
    }))).toBe('Factura BE 418 are un cont pe fiecare linie: o linie după o regulă, 2 linii cu contul facturii, păstrat la împărțire. Contul: 302.')
  })

  it('says how many lines are left when an invoice decided line by line is to check', () => {
    expect(describeEvent(line('account.to_review', { invoice_number: 'CO 1879', lines: 3, lines_left: 1 })))
      .toBe('Factura CO 1879 este de verificat: o linie nu are încă un cont.')
    expect(describeEvent(line('account.to_review', { invoice_number: 'CO 1879', lines: 3, lines_left: 2 })))
      .toBe('Factura CO 1879 este de verificat: 2 linii nu au încă un cont.')
  })

  it('tells how the invoices of a client are decided, line by line or whole', () => {
    expect(describeEvent(line('client.per_line', { client: 'Alfa SRL', cui: '12345674', per_line: true })))
      .toBe('Clientul Alfa SRL: fiecare linie a unei facturi primește contul ei.')
    expect(describeEvent(line('client.per_line', { client: 'Alfa SRL', cui: '12345674', per_line: false })))
      .toBe('Clientul Alfa SRL: un singur cont pentru toată factura, după linia cea mai mare.')
    expect(describeEvent(line('settings.jev_line_question', {}))).toBe('A fost schimbată întrebarea pusă lui Jev despre o linie.')
  })

  it('says when a rule, an account or a question is for the invoices a client issued', () => {
    expect(describeEvent(line('rule.added', { name: 'manoperă', cont: '704', kind: 'issued' })))
      .toBe('A fost adăugată regula „manoperă” (facturi emise), pentru contul 704.')
    expect(describeEvent(line('rule.changed', { name: 'combustibil', cont: '6022', kind: 'received' })))
      .toBe('A fost modificată regula „combustibil”, pentru contul 6022.')
    expect(describeEvent(line('account.saved', { cont: '704', kind: 'issued' })))
      .toBe('Contul 704 a fost adăugat sau modificat în lista lui Jev pentru facturile emise.')
    expect(describeEvent(line('account.removed', { cont: '628' }))).toBe('Contul 628 a fost scos din lista lui Jev.')
    expect(describeEvent(line('settings.jev_issued_question', {})))
      .toBe('A fost schimbată întrebarea pusă lui Jev despre o factură emisă.')
    expect(describeEvent(line('settings.jev_issued_line_question', {})))
      .toBe('A fost schimbată întrebarea pusă lui Jev despre o linie a unei facturi emise.')
  })

  it('tells which line Jev answered about', () => {
    expect(describeEvent(line('jev.answered', { cost_usd: 0.42, line: 2 }, { duration_ms: 820 })).replace(/\s/g, ' '))
      .toBe('Jev a răspuns pentru linia 2 în 0,8 s. Cost: 0,42 $.')
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
    // Since the issued invoices are counted apart, only the received ones are "new".
    expect(say('sync.auto_finished', { status: 'ok', new: 9, received: 2, issued: 7, review: 1 }))
      .toBe('Descărcarea automată s-a terminat: 2 facturi primite noi, 7 emise noi, 1 de verificat.')
    expect(say('sync.auto_finished', { status: 'ok', new: 3, received: 0, issued: 3, review: 0 }))
      .toBe('Descărcarea automată s-a terminat: nicio factură primită, 3 emise noi.')
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

describe('the files for SAGA in the journal', () => {
  const line = (event: string, data: Record<string, unknown>) =>
    describeEvent({ event, data, message: '' } as unknown as JournalLine)

  it('says whether the issued invoices are shown', () => {
    expect(line('settings.show_issued', { shown: true })).toBe('De acum, facturile emise de clienți se văd pe ecranul fiecărui client.')
    expect(line('settings.show_issued', { shown: false })).toBe('De acum, facturile emise de clienți nu se mai văd pe ecran.')
    expect(line('settings.show_issued', { shown: true, no_effect: true })).toBe(
      'A fost schimbată setarea veche „Arată facturile emise”. Ea nu mai schimbă nimic: facturile emise au fila lor.',
    )
  })

  it('says which way was chosen', () => {
    expect(line('settings.saga_file_per', { per: 'client' })).toBe('De acum, facturile gata de import ale fiecărui client se scriu într-un singur fișier pentru SAGA.')
    expect(line('settings.saga_file_per', { per: 'invoice' })).toBe('De acum, fiecare factură gata de import are fișierul ei pentru SAGA.')
  })

  it('says whose files could not be written, and when they are up to date again', () => {
    expect(line('saga.files_failed', { client: 'Alfa SRL', cui: '1' })).toBe('Fișierele pentru SAGA ale clientului Alfa SRL nu au putut fi scrise. Programul încearcă din nou la următoarea schimbare.')
    expect(line('saga.files_written', { cui: '12345674' })).toBe('Fișierele pentru SAGA ale clientului CUI 12345674 sunt din nou la zi.')
    expect(line('saga.folder_moved', { client: 'Alfa Construct SRL', cui: '12345674', old: '12345674', new: 'Alfa Construct SRL - 12345674' }))
      .toBe('Folderul pentru SAGA al clientului Alfa Construct SRL a fost mutat: din „12345674” în „Alfa Construct SRL - 12345674”.')
    const left = { client: 'Alfa Construct SRL', cui: '12345674', old: '12345674', new: 'Alfa Construct SRL - 12345674' }
    expect(line('saga.folder_left', { ...left, empty: false }))
      .toBe('Folderul vechi „12345674” al clientului Alfa Construct SRL a rămas: are în el fișiere pe care nu le-a scris programul. Fișierele clientului se scriu în „Alfa Construct SRL - 12345674”. Folderul vechi dispare singur după ce îl goliți.')
    expect(line('saga.folder_left', { ...left, empty: true }))
      .toBe('Folderul vechi „12345674” al clientului Alfa Construct SRL a rămas: îl folosește alt program. Fișierele clientului se scriu în „Alfa Construct SRL - 12345674”. Programul șterge singur folderul vechi când poate.')
  })
})

describe('an import confirmed in SAGA', () => {
  it('says who confirmed it and how many invoices were marked', () => {
    expect(describeEvent(line('saga.imported', { client: 'Alfa SRL', cui: '1', invoices: 12, source: 'automation' })))
      .toBe('Importul în SAGA al clientului Alfa SRL a fost confirmat din automatizare: 12 facturi marcate ca importate, iar fișierul este acum în arhivă.')
    expect(describeEvent(line('saga.imported', { cui: '12345674', invoices: 1, source: 'screen' })))
      .toBe('Importul în SAGA al clientului CUI 12345674 a fost confirmat de pe ecran: o factură marcată ca importată, iar fișierul este acum în arhivă.')
    expect(describeEvent(line('saga.imported', { cui: '1', invoices: 25, source: 'screen' }))).toContain('25 de facturi marcate')
  })
})
