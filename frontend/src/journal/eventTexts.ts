// The program writes each kind of event with a code and an English line. Here the codes it
// is known to write become Romanian sentences; anything else keeps the English line.

import { newInvoices } from '../newInvoices'
import { countDoing, countOf, formatPercent, formatUsd } from '../format'
import { describePeriod, describeWhen } from '../schedule/scheduleTexts'
import type { JournalLine, SchedulePeriod } from '../types'

export const LEVEL_NAMES: Record<JournalLine['level'], string> = {
  detail: 'Detaliu', info: 'Informație', warning: 'Atenție', error: 'Eroare',
}

const AREA_NAMES: Record<string, string> = {
  sync: 'Descărcări', anaf: 'ANAF', accounts: 'Alegerea conturilor', jev: 'Jev', rules: 'Reguli',
  clients: 'Clienți', settings: 'Setări și chei', backup: 'Copii de siguranță', update: 'Actualizări',
  page: 'Pagina', program: 'Programul',
}
/** The areas a person can narrow the journal to, in the order of the list. */
export const AREAS = Object.entries(AREA_NAMES)

export function areaName(area: string): string {
  return AREA_NAMES[area] ?? area
}

const KEY_NAMES: Record<string, string> = {
  openrouter_api_key: 'cheia OpenRouter', anaf_client_id: 'Client ID de la ANAF', anaf_client_secret: 'Client Secret de la ANAF',
}

/** "0,8 s" or "45 ms". */
export function formatDuration(milliseconds: number | null): string {
  if (milliseconds === null) return ''
  // Under a tenth of a second the seconds would read "0,0 s".
  return milliseconds < 100 ? `${milliseconds} ms` : `${(milliseconds / 1000).toFixed(1).replace('.', ',')} s`
}

type Data = Record<string, unknown>
const text = (value: unknown) => (value === undefined || value === null ? '' : String(value))
const who = (data: Data) => text(data.client) || `CUI ${text(data.cui)}`
const invoice = (data: Data) => `Factura ${text(data.invoice_number) || text(data.id)}`
// A rule or an account for the invoices a client issued says so; one for received invoices says nothing more.
const forIssued = (data: Data) => (data.kind === 'issued' ? ' pentru facturile emise' : '')
const issuedNote = (data: Data) => (data.kind === 'issued' ? ' (facturi emise)' : '')

const HOW_A_COPY_WAS_MADE: Record<string, string> = {
  manual: 'la cererea dumneavoastră', auto: 'automat', 'before-restore': 'înaintea restaurării',
}

// The causes a failed automatic download names in the journal; any other is in the technical details.
const AUTO_FAILURES: Record<string, string> = {
  login_needed: 'trebuie să vă conectați din nou la ANAF',
  anaf_limit_reached: 'ANAF a limitat numărul de cereri pentru azi',
  anaf_error: 'ANAF a răspuns cu o eroare',
  invalid_input: 'ANAF nu mai păstrează facturile din perioada aleasă',
}

const SENTENCES: Record<string, (data: Data, line: JournalLine) => string> = {
  'program.started': (data) => `Programul a pornit. Versiunea ${text(data.version)}.`,
  'program.stopped': () => 'Programul s-a oprit.',
  'page.request': (data) => `Pagina a cerut ${text(data.method)} ${text(data.path)} și a primit răspunsul ${text(data.status)}.`,

  'sync.started': (data) => {
    const days = Number(data.window_days)
    return `A început descărcarea pentru ${who(data)}, pentru ${days === 1 ? 'ultima zi' : `ultimele ${countOf(days, 'o zi', 'zile')}`}.`
  },
  'sync.finished': (data) => {
    // Lines written before the issued invoices were counted apart carry only `new`.
    const came = newInvoices(Number(data.received ?? data.new), Number(data.issued) || 0)
    const failed = Number(data.failed) ? countOf(Number(data.failed), 'una nereușită', 'nereușite') : 'niciuna nereușită'
    return `Descărcarea pentru ${who(data)} s-a terminat: ${[...(came.length ? came : ['nicio factură nouă']), failed].join(', ')}.`
  },
  'sync.failed': (data) => `Descărcarea pentru ${who(data)} nu a reușit.`,
  'sync.message_failed': () => 'Un mesaj de la ANAF nu a putut fi salvat. Se încearcă din nou la următoarea descărcare.',

  'schedule.saved': (data) => {
    if (!data.enabled) return 'Descărcarea automată a fost oprită.'
    // Lines written before the period existed do not carry one.
    const period = data.period ? `, pentru ${describePeriod(data.period as SchedulePeriod)}` : ''
    return `Descărcarea automată a fost pornită: ${describeWhen(data.days as number[], data.times as string[])}${period}.`
  },
  'sync.auto_started': (data) =>
    `Descărcarea automată a început.${Number(data.attempt) > 1 ? ` Este încercarea ${text(data.attempt)} din 4.` : ''}`,
  'sync.auto_finished': (data) => {
    // Lines written before the issued invoices were counted apart carry only `new`.
    const found = [
      ...newInvoices(Number(data.received ?? data.new), Number(data.issued) || 0),
      ...(Number(data.review) > 0 ? [`${text(data.review)} de verificat`] : []),
    ]
    switch (data.status) {
      case 'ok':
        return `Descărcarea automată s-a terminat: ${found.length ? found.join(', ') : 'nimic nou'}.`
      case 'partial':
        return `Descărcarea automată s-a terminat: ${found.length ? found.join(', ') : 'nimic nou'}. Nu a fost completă; se reia la următoarea descărcare.`
      case 'unreachable':
        return Number(data.attempt) >= 4
          ? 'Descărcarea automată nu a ajuns la ANAF. A fost ultima încercare pentru această oră.'
          : 'Descărcarea automată nu a ajuns la ANAF. Programul mai încearcă peste un sfert de oră.'
      default: {
        const cause = AUTO_FAILURES[text(data.error)]
        return `Descărcarea automată nu a reușit${cause ? `: ${cause}` : ''}.`
      }
    }
  },

  'sync.record_unsaved': () => 'Descărcarea automată s-a terminat, dar rezultatul ei nu a putut fi salvat.',

  'anaf.call': (_, line) => `ANAF a răspuns${line.duration_ms === null ? '' : ` în ${formatDuration(line.duration_ms)}`}.`,
  'anaf.unreachable': () => 'Nu am putut ajunge la ANAF. Verificați conexiunea la internet.',
  'anaf.connected': () => 'Conectarea la ANAF a reușit.',
  'anaf.certificate_asked': () => 'Programul a cerut certificatul de la Windows.',
  'anaf.renewed': () => 'Conectarea la ANAF a fost reînnoită automat, fără tokenul USB.',

  'classification.again': (data) => {
    const parts = [
      countOf(Number(data.total), 'o factură', 'facturi'),
      Number(data.classified) ? countDoing(Number(data.classified), 'una a primit cont', 'au primit cont') : 'niciuna nu a primit cont',
      ...(Number(data.review) ? [countDoing(Number(data.review), 'una rămâne de verificat', 'rămân de verificat')] : []),
      ...(Number(data.waiting) ? [countDoing(Number(data.waiting), 'una așteaptă încă răspunsul lui Jev', 'așteaptă încă răspunsul lui Jev')] : []),
    ]
    return `Facturile de verificat ale clientului ${who(data)} au fost clasificate din nou${data.jev_asked ? '' : ', doar după reguli'}: ` +
      `${parts.join(', ')}.${data.jev_stopped ? ' Jev nu a mai răspuns.' : ''}`
  },
  'account.by_rule': (data) => `${invoice(data)} a primit contul ${text(data.cont)}, după o regulă a dumneavoastră.`,
  'account.by_jev': (data) =>
    `${invoice(data)} a primit contul ${text(data.cont)}, ales de Jev (sigur ${formatPercent(Number(data.confidence))}).`,
  'account.by_person': (data) => `${invoice(data)} a primit contul ${text(data.cont)}, ales de dumneavoastră.`,
  'account.to_review': (data) =>
    data.lines_left
      ? `${invoice(data)} este de verificat: ${countOf(Number(data.lines_left), 'o linie nu are', 'linii nu au')} încă un cont.`
      : `${invoice(data)} este de verificat: trebuie să îi alegeți contul.`,
  'account.by_lines': (data) => {
    const parts = [
      [data.by_rules, 'o linie după o regulă', 'linii după reguli'],
      [data.by_jev, 'o linie de la Jev', 'linii de la Jev'],
      [data.by_person, 'o linie aleasă de dumneavoastră', 'linii alese de dumneavoastră'],
      [data.following, 'o linie cu contul liniei celei mai mari', 'linii cu contul liniei celei mai mari'],
      [data.as_invoice, 'o linie cu contul facturii, păstrat la împărțire', 'linii cu contul facturii, păstrat la împărțire'],
    ]
      .filter(([count]) => Number(count) > 0)
      .map(([count, one, many]) => countOf(Number(count), String(one), String(many)))
    const accounts = Array.isArray(data.accounts) ? data.accounts.map(String) : []
    const named = accounts.length === 1 ? `Contul: ${accounts[0]}.` : `Conturile: ${accounts.join(', ')}.`
    return `${invoice(data)} are un cont pe fiecare linie: ${parts.join(', ')}. ${named}`
  },
  'invoices.marked_imported': (data) =>
    `${countOf(Number(data.invoices), 'O factură a fost bifată ca importată', 'facturi au fost bifate ca importate')} în SAGA.`,
  'invoices.unmarked': (data) =>
    `${countOf(Number(data.invoices), 'O factură nu mai este bifată ca importată', 'facturi nu mai sunt bifate ca importate')} în SAGA.`,

  // A cost the program did not write is unknown. Turned into a number, a missing one would
  // read "NaN $" and an empty one "0,00 $".
  'jev.answered': (data, line) =>
    `Jev a răspuns${typeof data.line === 'number' ? ` pentru linia ${data.line}` : ''}${line.duration_ms === null ? '' : ` în ${formatDuration(line.duration_ms)}`}. Cost: ${typeof data.cost_usd === 'number' ? formatUsd(data.cost_usd) : 'necunoscut'}.`,
  'jev.failed': () => 'Jev nu a dat un răspuns care să poată fi folosit.',

  'rule.tested': (data) =>
    data.decided_by === 'rule' || data.decided_by === 'jev'
      ? `A fost încercată o factură de probă: contul ${text(data.cont)}, ales de ${data.decided_by === 'rule' ? 'o regulă' : 'Jev'}.`
      : 'A fost încercată o factură de probă: nu a primit niciun cont.',
  'rule.added': (data) => `A fost adăugată regula „${text(data.name)}”${issuedNote(data)}, pentru contul ${text(data.cont)}.`,
  'rule.changed': (data) => `A fost modificată regula „${text(data.name)}”${issuedNote(data)}, pentru contul ${text(data.cont)}.`,
  'rule.removed': () => 'A fost ștearsă o regulă.',
  'rule.proposal_turned_down': () => 'Ați ales „Nu acum” la o regulă propusă.',
  'account.saved': (data) => `Contul ${text(data.cont)} a fost adăugat sau modificat în lista lui Jev${forIssued(data)}.`,
  'account.removed': (data) => `Contul ${text(data.cont)} a fost scos din lista lui Jev${forIssued(data)}.`,

  'client.saved': (data) => `Clientul ${who(data)} a fost adăugat sau redenumit.`,
  'client.switched': (data) =>
    data.enabled
      ? `Clientul ${who(data)} a fost pornit: facturile lui se descarcă din nou.`
      : `Clientul ${who(data)} a fost oprit: facturile lui nu se mai descarcă.`,
  'client.per_line': (data) =>
    data.per_line
      ? `Clientul ${who(data)}: fiecare linie a unei facturi primește contul ei.`
      : `Clientul ${who(data)}: un singur cont pentru toată factura, după linia cea mai mare.`,
  'client.removed': (data) => `Clientul cu CUI ${text(data.cui)} a fost scos din listă.`,
  'clients.imported': (data) =>
    `Clienți importați din ${text(data.file)}: adăugați: ${text(data.added)}, modificați: ${text(data.updated)}, respinși: ${text(data.rejected)}.`,

  'settings.secret_changed': (data) => `A fost schimbată o cheie: ${KEY_NAMES[text(data.name)] ?? text(data.name)}.`,
  'settings.changed': (data) => (data.name === 'saga_dir' ? 'A fost schimbat folderul pentru SAGA.' : 'A fost schimbată o setare.'),
  'settings.saga_file_per': (data) =>
    data.per === 'invoice'
      ? 'De acum, fiecare factură gata de import are fișierul ei pentru SAGA.'
      : 'De acum, facturile gata de import ale fiecărui client se scriu într-un singur fișier pentru SAGA.',
  'settings.show_issued': (data) =>
    data.no_effect
      ? 'A fost schimbată setarea veche „Arată facturile emise”. Ea nu mai schimbă nimic: facturile emise au fila lor.'
      : data.shown
      ? 'De acum, facturile emise de clienți se văd pe ecranul fiecărui client.'
      : 'De acum, facturile emise de clienți nu se mai văd pe ecran.',
  'saga.files_failed': (data) =>
    `Fișierele pentru SAGA ale clientului ${who(data)} nu au putut fi scrise. Programul încearcă din nou la următoarea schimbare.`,
  'saga.imported': (data) =>
    `Importul în SAGA al clientului ${who(data)} a fost confirmat ${data.source === 'screen' ? 'de pe ecran' : 'din automatizare'}: ` +
    `${countOf(Number(data.invoices), 'o factură marcată', 'facturi marcate')} ca importat${Number(data.invoices) === 1 ? 'ă' : 'e'}, iar fișierul este acum în arhivă.`,
  'saga.files_written': (data) => `Fișierele pentru SAGA ale clientului ${who(data)} sunt din nou la zi.`,
  'settings.confidence': (data) => `Cât de sigur trebuie să fie Jev: acum ${formatPercent(Number(data.level_set))}.`,
  'settings.jev_question': () => 'A fost schimbată întrebarea pusă lui Jev.',
  'settings.jev_line_question': () => 'A fost schimbată întrebarea pusă lui Jev despre o linie.',
  'settings.jev_issued_question': () => 'A fost schimbată întrebarea pusă lui Jev despre o factură emisă.',
  'settings.jev_issued_line_question': () => 'A fost schimbată întrebarea pusă lui Jev despre o linie a unei facturi emise.',

  'backup.made': (data) => `A fost făcută o copie de siguranță, ${HOW_A_COPY_WAS_MADE[text(data.kind)] ?? 'automat'}.`,
  // Only a folder known to be missing is named as the cause; anything else is in the technical details.
  'backup.failed': (data) =>
    !data.folder
      ? 'Copia de siguranță nu a reușit.'
      : data.folder_found === false
        ? `Copia de siguranță nu a reușit: folderul ${text(data.folder)} nu a fost găsit.`
        : `Copia de siguranță în folderul ${text(data.folder)} nu a reușit.`,
  'backup.folder_set': (data) => `Folderul copiilor de siguranță este acum ${text(data.folder)}.`,
  'backup.removed_old': (data) => `${countOf(Number(data.removed), 'Cea mai veche copie a fost ștearsă', 'copii vechi au fost șterse')}, ca să rămână cel mult 25.`,
  'restore.finished': (data) => `Baza de date a fost restaurată din copia ${text(data.name)}.`,
  'restore.failed': () => 'Restaurarea nu a reușit. Baza de date a rămas cea de dinainte.',
  'restore.not_restarted': () => 'După restaurare programul nu a pornit singur. Faceți dublu clic pe „AutoSaga” de pe Desktop.',
  'restore.kept_aside': (data) =>
    `Baza de date de dinainte nu a putut fi copiată în folderul copiilor; a fost păstrată lângă program, în fișierul ${text(data.kept_as)}.`,

  'update.finished': (data) => `Programul a fost actualizat la versiunea ${text(data.release).replace(/^v/, '')}.`,
  'update.failed': () => 'Actualizarea programului nu a reușit. A rămas la versiunea pe care o avea.',
  'update.not_restarted': () => 'După actualizare programul nu a pornit singur. Faceți dublu clic pe „AutoSaga” de pe Desktop.',
}

/** The line as the person reads it: Romanian for the events the program is known to write. */
export function describeEvent(line: JournalLine): string {
  const say = line.event ? SENTENCES[line.event] : undefined
  return say ? say(line.data, line) : line.message
}
