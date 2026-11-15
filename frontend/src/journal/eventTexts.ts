// The program writes each kind of event with a code and an English line. Here the codes it
// is known to write become Romanian sentences; anything else keeps the English line.

import { countOf, formatPercent, formatUsd } from '../format'
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

const HOW_A_COPY_WAS_MADE: Record<string, string> = {
  manual: 'la cererea dumneavoastră', auto: 'automat', 'before-restore': 'înaintea restaurării',
}

// The causes a failed automatic download names in the journal; any other is in the technical details.
const AUTO_FAILURES: Record<string, string> = {
  login_needed: 'trebuie să vă conectați din nou la ANAF',
  anaf_limit_reached: 'ANAF a limitat numărul de cereri pentru azi',
  anaf_error: 'ANAF a răspuns cu o eroare',
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
    const fresh = Number(data.new) ? countOf(Number(data.new), 'o factură nouă', 'facturi noi') : 'nicio factură nouă'
    const failed = Number(data.failed) ? countOf(Number(data.failed), 'una nereușită', 'nereușite') : 'niciuna nereușită'
    return `Descărcarea pentru ${who(data)} s-a terminat: ${fresh}, ${failed}.`
  },
  'sync.failed': (data) => `Descărcarea pentru ${who(data)} nu a reușit.`,
  'sync.message_failed': () => 'Un mesaj de la ANAF nu a putut fi salvat. Se încearcă din nou la următoarea descărcare.',

  'schedule.saved': (data) => {
    if (!data.enabled) return 'Descărcarea automată a fost oprită.'
    // Lines written before the period existed do not carry one.
    const period = data.period ? `, cu ${describePeriod(data.period as SchedulePeriod)}` : ''
    return `Descărcarea automată a fost pornită: ${describeWhen(data.days as number[], data.times as string[])}${period}.`
  },
  'sync.auto_started': (data) =>
    `Descărcarea automată a început.${Number(data.attempt) > 1 ? ` Este încercarea ${text(data.attempt)} din 4.` : ''}`,
  'sync.auto_finished': (data) => {
    const found = [
      Number(data.new) > 0 && countOf(Number(data.new), 'o factură nouă', 'facturi noi'),
      Number(data.review) > 0 && `${text(data.review)} de verificat`,
    ].filter(Boolean) as string[]
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

  'account.by_rule': (data) => `${invoice(data)} a primit contul ${text(data.cont)}, după o regulă a dumneavoastră.`,
  'account.by_jev': (data) =>
    `${invoice(data)} a primit contul ${text(data.cont)}, ales de Jev (sigur ${formatPercent(Number(data.confidence))}).`,
  'account.by_person': (data) => `${invoice(data)} a primit contul ${text(data.cont)}, ales de dumneavoastră.`,
  'account.to_review': (data) => `${invoice(data)} este de verificat: trebuie să îi alegeți contul.`,
  'invoices.marked_imported': (data) =>
    `${countOf(Number(data.invoices), 'O factură a fost bifată ca importată', 'facturi au fost bifate ca importate')} în SAGA.`,
  'invoices.unmarked': (data) =>
    `${countOf(Number(data.invoices), 'O factură nu mai este bifată ca importată', 'facturi nu mai sunt bifate ca importate')} în SAGA.`,

  // A cost the program did not write is unknown. Turned into a number, a missing one would
  // read "NaN $" and an empty one "0,00 $".
  'jev.answered': (data, line) =>
    `Jev a răspuns${line.duration_ms === null ? '' : ` în ${formatDuration(line.duration_ms)}`}. Cost: ${typeof data.cost_usd === 'number' ? formatUsd(data.cost_usd) : 'necunoscut'}.`,
  'jev.failed': () => 'Jev nu a dat un răspuns care să poată fi folosit.',

  'rule.tested': (data) =>
    data.decided_by === 'rule' || data.decided_by === 'jev'
      ? `A fost încercată o factură de probă: contul ${text(data.cont)}, ales de ${data.decided_by === 'rule' ? 'o regulă' : 'Jev'}.`
      : 'A fost încercată o factură de probă: nu a primit niciun cont.',
  'rule.added': (data) => `A fost adăugată regula „${text(data.name)}”, pentru contul ${text(data.cont)}.`,
  'rule.changed': (data) => `A fost modificată regula „${text(data.name)}”, pentru contul ${text(data.cont)}.`,
  'rule.removed': () => 'A fost ștearsă o regulă.',
  'rule.proposal_turned_down': () => 'Ați ales „Nu acum” la o regulă propusă.',
  'account.saved': (data) => `Contul ${text(data.cont)} a fost adăugat sau modificat în lista lui Jev.`,
  'account.removed': (data) => `Contul ${text(data.cont)} a fost scos din lista lui Jev.`,

  'client.saved': (data) => `Clientul ${who(data)} a fost adăugat sau redenumit.`,
  'client.switched': (data) =>
    data.enabled
      ? `Clientul ${who(data)} a fost pornit: facturile lui se descarcă din nou.`
      : `Clientul ${who(data)} a fost oprit: facturile lui nu se mai descarcă.`,
  'client.removed': (data) => `Clientul cu CUI ${text(data.cui)} a fost scos din listă.`,
  'clients.imported': (data) =>
    `Clienți importați din ${text(data.file)}: adăugați: ${text(data.added)}, modificați: ${text(data.updated)}, respinși: ${text(data.rejected)}.`,

  'settings.secret_changed': (data) => `A fost schimbată o cheie: ${KEY_NAMES[text(data.name)] ?? text(data.name)}.`,
  'settings.changed': (data) => (data.name === 'saga_dir' ? 'A fost schimbat folderul pentru SAGA.' : 'A fost schimbată o setare.'),
  'settings.confidence': (data) => `Cât de sigur trebuie să fie Jev: acum ${formatPercent(Number(data.level_set))}.`,
  'settings.jev_question': () => 'A fost schimbată întrebarea pusă lui Jev.',

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
