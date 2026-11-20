// Every call the page makes to the Python program, in one place.

import type {
  AppSettings, AuthStatus, BackupStatus, ClassifyAgainResult, Client, CostGroup, Costs, Decision, ImportResult, Invoice, InvoiceKind,
  InvoiceView, JevCall, JournalLine,
  ProposedRules,
  RuleEvidence, RuleFields, RuleTestResult, RulesOverview, SagaFilePer, SagaImport, SagaImportDetail, SagaState, SchedulePeriod,
  ScheduleStatus, Secret,
  SyncResult, WipeResult, TechnicalCounts, TechnicalRecord, TechnicalWhole, TrialAsk, UpdateStatus, WaitingFiles, Where,
} from './types'

/** What the program answers when it refuses: a stable code and an English explanation. */
export class ApiError extends Error {
  readonly code: string

  constructor(code: string, message: string) {
    super(message)
    this.code = code
  }
}

/**
 * Sent with every call. In server mode the program takes a change only with it: another site can
 * make a browser post a form to the program, but cannot add a header of its own.
 */
const FROM_THE_PAGE = { 'X-AutoSaga-Page': '1' }

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const isFile = body instanceof Blob
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers: body === undefined || isFile ? FROM_THE_PAGE : { ...FROM_THE_PAGE, 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : isFile ? body : JSON.stringify(body),
    })
  } catch {
    throw new ApiError('unreachable', 'The program did not answer.')
  }
  const reply = await response.json().catch(() => null)
  if (!response.ok || !reply?.ok) {
    throw new ApiError(reply?.error?.code ?? 'internal_error', reply?.error?.message ?? response.statusText)
  }
  return reply as T
}

/** A file the program serves as it is on disk. A refusal comes as the usual answer, with its code. */
async function served(path: string): Promise<Response> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, { headers: FROM_THE_PAGE })
  } catch {
    throw new ApiError('unreachable', 'The program did not answer.')
  }
  if (!response.ok) {
    const reply = await response.json().catch(() => null)
    throw new ApiError(reply?.error?.code ?? 'internal_error', reply?.error?.message ?? response.statusText)
  }
  return response
}

/** Such a file as text, to show. */
async function text(path: string): Promise<string> {
  return (await served(path)).text()
}

/** With a waiting file: the version of the bytes given, which a confirmation of that file sends back. */
const FILE_VERSION = 'X-AutoSaga-File-Version'

/** A query string without the empty values. */
function query(params: Record<string, string | number | boolean | undefined | null>): string {
  const filled = Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== '')
  return filled.length ? `?${new URLSearchParams(filled.map(([key, value]) => [key, String(value)]))}` : ''
}

// `cover_gap` makes the days a minimum: the program reaches further back when the last
// complete download was longer ago, so no day is skipped.
export type SyncPeriod = { days: number; cover_gap: true } | { start: string; end: string }
export type CostRange = { since?: string; until?: string }
/** What narrows the journal. `trace` shows one whole operation. */
export type JournalFilter = {
  details?: boolean
  problems?: boolean
  area?: string
  q?: string
  since?: string
  trace?: string
  /** The technical view: the lines come with how many requests each operation made, and the saved file holds them. */
  technical?: boolean
}

/** The most Jev calls the program lists at once. */
export const MOST_CALLS_LISTED = 1000
/** The most journal lines the program gives in one answer. */
const MOST_LINES_AT_ONCE = 1000
/** The most technical records the program gives in one answer. */
const MOST_RECORDS_AT_ONCE = 2000

export const api = {
  authStatus: () => call<AuthStatus>('GET', '/auth/status'),
  startLogin: () => call<{ authorize_url: string }>('POST', '/auth/login/start'),
  loginWithCertificate: () => call<AuthStatus>('POST', '/auth/login/certificate'),
  finishLogin: (address: string) => call<AuthStatus>('POST', '/auth/login/finish', { address }),

  sagaFolder: () => call<AppSettings>('GET', '/settings'),
  /** Local or server mode, whether this browser is on the program's computer, and how the PCs reach the folder for SAGA. */
  where: () => call<Where>('GET', '/where'),
  /**
   * The folder, one file per client or per invoice, or both; what is left out stays as it
   * is. `problems` names the clients whose files could not be written again.
   */
  setSagaOutput: (changes: { saga_folder?: string; saga_file_per?: SagaFilePer }) =>
    call<AppSettings & { problems: { cui: string }[] }>('PUT', '/settings', changes),
  /** Shows or hides the invoices the clients issued, for every client. */
  /** Brings one client's files for SAGA up to date, after they could not be. */
  writeSagaFiles: (cui: string) => call<{ problems: { cui: string }[] }>('POST', '/saga-files/write', { cui }),
  /** `purpose` says which folder is being picked, so the dialog is titled for it and opens where that folder is. */
  chooseFolder: (purpose?: 'backups') =>
    call<{ folder: string | null }>('POST', `/settings/choose-folder${query({ purpose })}`),
  /** Opens the folder that invoice's SAGA file is in. */
  openFolderOf: (invoiceId: string) => call('POST', '/folders/open', { invoice_id: invoiceId }),

  clients: () => call<{ clients: Client[] }>('GET', '/clients'),
  saveClient: (cui: string, name: string) => call('POST', '/clients', { cui, name }),
  setClientEnabled: (cui: string, enabled: boolean) =>
    call<{ clients: Client[] }>('PUT', `/clients/${cui}/enabled`, { enabled }),
  /** Every client switched on, or off, at once: what each client's own switch does, for the whole list. */
  setAllClientsEnabled: (enabled: boolean) => call<{ clients: Client[] }>('PUT', '/clients/enabled', { enabled }),
  /** An account for each line of this client's invoices (true), or one for the whole invoice. */
  setClientPerLine: (cui: string, enabled: boolean) =>
    call<{ clients: Client[] }>('PUT', `/clients/${cui}/per-line`, { enabled }),
  removeClient: (cui: string) => call('DELETE', `/clients/${cui}`),
  importClients: (file: File) =>
    call<ImportResult>('POST', `/clients/import${query({ filename: file.name })}`, file),

  schedule: () => call<ScheduleStatus>('GET', '/sync/schedule'),
  saveSchedule: (schedule: { enabled: boolean; days: number[]; times: string[]; period: SchedulePeriod }) =>
    call<ScheduleStatus>('PUT', '/sync/schedule', schedule),

  sync: (cui: string, period: SyncPeriod) => call<SyncResult>('POST', '/sync', { cui, ...period }),

  /** A client's received invoices, with how its files for SAGA stand and how many invoices it issued. */
  receivedInvoices: (cui: string) =>
    call<{ invoices: Invoice[]; saga: SagaState; issued_count: number }>('GET', `/invoices${query({ cui, type: 'primita' })}`),
  /** The invoices the client issued itself. They get accounts and go to SAGA like the received ones. */
  issuedInvoices: (cui: string) =>
    call<{ invoices: Invoice[] }>('GET', `/invoices${query({ cui, type: 'trimisa' })}`),
  invoiceView: (id: string) => call<InvoiceView>('GET', `/invoices/${id}/view`),
  /**
   * Decided again from the start: the rules then Jev, or with `ask` 'jev_only' Jev alone. `line`: that line
   * alone; `perLine`: line by line or with one account (left out: as the client is set).
   */
  classify: (id: string, force = false, how: { ask?: TrialAsk; line?: number; perLine?: boolean } = {}) =>
    call('POST', `/invoices/${id}/classify`, { force, ask: how.ask, line: how.line, per_line: how.perLine }),
  /** An invoice with one account becomes one decided line by line, each line starting with that account. */
  splitIntoLines: (id: string) => call('POST', `/invoices/${id}/split`),
  /** How the invoice got its account, each time it changed, the newest first. */
  decisions: (id: string) => call<{ decisions: Decision[] }>('GET', `/invoices/${id}/decisions`),
  /** The client's invoices to check, or waiting for Jev, back through the rules and, with `jev`, Jev. */
  classifyAgain: (cui: string, jev: boolean) => call<ClassifyAgainResult>('POST', `/clients/${cui}/classify-again`, { jev }),
  /** Without `line`: Jev's proposal for the invoice, or for every line left on an invoice decided line by line. */
  acceptSuggestion: (id: string, line?: number) => call('POST', `/invoices/${id}/cont`, { accept: true, line }),
  /** Without `line`: the account of the whole invoice, or of every line on an invoice decided line by line. */
  setCont: (id: string, cont: string, force = false, line?: number) =>
    call('POST', `/invoices/${id}/cont`, { cont, force, line }),
  markUploaded: (ids: string[], uploaded = true) => call('POST', '/invoices/uploaded', { ids, uploaded }),
  /**
   * SAGA has imported the client's files: every invoice in them is marked as imported and the
   * files go to the archive. Refused with `saga_files_changed` when they changed since `version`.
   * With `file`, that one waiting file alone, and `version` is that file's own.
   */
  confirmSagaImport: (cui: string, version: string | null, file?: string) =>
    call<{
      archive: { id: number; invoices: number; files: { name: string; path: string }[] } | null
      /** With an archive: all the client's files together, as they stood when it was confirmed and as those left stand. */
      versions?: { before: string | null; after: string | null }
    }>('POST', `/saga-files/${cui}/imported`, { version, source: 'screen', file }),
  /** One client's files for SAGA as they are now, with their version. */
  /** What waits for SAGA for one client: its folder, its files with their invoices, and their version. */
  sagaFiles: (cui: string) => call<WaitingFiles>('GET', `/saga-files/${cui}`),
  /** One waiting file, as it is in the client's folder now. */
  sagaFileXml: (cui: string, name: string) => text(`/saga-files/${cui}/files/${encodeURIComponent(name)}`),
  /**
   * The same file to save on this computer, with the version of the bytes given. Fetched by the
   * page, not followed as a link: a file that is gone is said on the page, and the call carries
   * the page's header like every other.
   */
  sagaFile: async (cui: string, name: string): Promise<{ blob: Blob; version: string | null }> => {
    const response = await served(`/saga-files/${cui}/files/${encodeURIComponent(name)}`)
    return { blob: await response.blob(), version: response.headers.get(FILE_VERSION) }
  },
  sagaArchive: (cui: string) => call<{ imports: SagaImport[] }>('GET', `/saga-archive${query({ cui })}`),
  sagaArchiveEntry: (id: number) => call<{ import: SagaImportDetail }>('GET', `/saga-archive/${id}`),
  /** Where the browser saves a file of a confirmed import from, as SAGA got it. */
  sagaArchiveFileAddress: (id: number, name: string) => `/api/saga-archive/${id}/files/${encodeURIComponent(name)}`,
  openSagaArchive: (id: number) => call('POST', `/saga-archive/${id}/open`),

  rules: () => call<RulesOverview>('GET', '/rules'),
  addRule: (rule: RuleFields) => call('POST', '/rules', rule),
  changeRule: (id: number, rule: RuleFields) => call('PUT', `/rules/${id}`, rule),
  deleteRule: (id: number) => call('DELETE', `/rules/${id}`),
  moveRule: (id: number, up: boolean) => call('POST', `/rules/${id}/move`, { up }),
  proposedRules: () => call<ProposedRules>('GET', '/rules/suggestions'),
  /** Tries a rule on the invoices given an account lately. Saves nothing. */
  tryRule: (conditions: { keywords: string[]; supplier_cuis: string[] }) =>
    call<RuleEvidence & { days: number }>('POST', '/rules/preview', conditions),
  /** Puts a made-up invoice through the path a real one takes. Saves nothing but what asking Jev cost. */
  testRules: (body: unknown) => call<RuleTestResult>('POST', '/rules/test', body),
  /** "Nu acum": no rule is proposed for these invoices again, unless their account changes. */
  turnDownProposal: (invoiceIds: string[]) =>
    call('POST', '/rules/suggestions/dismiss', { invoice_ids: invoiceIds }),
  saveAccount: (cont: string, description: string, kind: InvoiceKind = 'received') =>
    call('PUT', `/accounts/${cont}`, { description, kind }),
  deleteAccount: (cont: string, kind: InvoiceKind = 'received') => call('DELETE', `/accounts/${cont}${query({ kind })}`),
  setJevSettings: (settings: {
    min_confidence?: number
    jev_instructions?: string
    jev_line_instructions?: string
    jev_issued_instructions?: string
    jev_issued_line_instructions?: string
  }) => call('PUT', '/classification/settings', settings),

  costs: (range: CostRange, group: CostGroup) =>
    call<Costs>('GET', `/classification/costs${query({ ...range, group })}`),
  jevCalls: (range: CostRange) =>
    call<{ calls: JevCall[] }>('GET', `/classification/calls${query({ ...range, limit: MOST_CALLS_LISTED })}`),

  backups: () => call<BackupStatus>('GET', '/backups'),
  setBackupFolder: (folder: string) => call<BackupStatus>('PUT', '/backups/folder', { folder }),
  makeBackup: () => call('POST', '/backups'),
  /** The program stops, puts the snapshot in place of the database and starts again. */
  restoreBackup: (name: string) => call('POST', '/backups/restore', { name }),
  openBackupFolder: () => call('POST', '/backups/open-folder'),
  wipeData: () => call<WipeResult>('POST', '/backups/wipe'),

  /** One operation is asked for as whole as the program gives it: it is read from its first step. */
  journal: (filter: JournalFilter, before?: number) =>
    call<{ events: JournalLine[]; has_more: boolean; technical?: TechnicalCounts }>(
      'GET', `/events${query({ ...filter, before, limit: filter.trace ? MOST_LINES_AT_ONCE : undefined })}`,
    ),
  /** One operation's requests and program records, newest first, without what was sent and received. */
  technical: (trace: string, before?: number) =>
    call<{ records: TechnicalRecord[]; has_more: boolean }>(
      'GET', `/events/technical${query({ trace, before, limit: MOST_RECORDS_AT_ONCE })}`,
    ),
  /** One request whole: its headers and bodies, or a program record's exception. */
  technicalRecord: (id: number) => call<{ record: TechnicalWhole }>('GET', `/events/technical/${id}`),
  /**
   * Where the browser saves the same lines as a text file from. Whether the details are in
   * it is always said: left out, the program would add them even when the page hides them.
   */
  journalFileAddress: (filter: JournalFilter) =>
    `/api/events/export${query({ ...filter, details: filter.details ?? false })}`,

  /** `lookNow` asks GitHub at once; otherwise the answer of the last twelve hours is given. */
  updateStatus: (lookNow = false) => call<UpdateStatus>('GET', `/update${query({ check: lookNow || undefined })}`),
  /** The program stops, moves to the newest release and starts again. Data and settings stay. */
  startUpdate: () => call('POST', '/update'),

  secrets: () => call<{ secrets: Secret[] }>('GET', '/secrets'),
  setSecret: (key: string, value: string) => call('PUT', `/secrets/${key}`, { value }),
}
