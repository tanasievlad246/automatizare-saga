// Every call the page makes to the Python program, in one place.

import type {
  AuthStatus, BackupStatus, Client, CostGroup, Costs, ImportResult, Invoice, InvoiceView, JevCall, JournalLine,
  ProposedRules,
  RuleEvidence, RuleFields, RuleTestResult, RulesOverview, Secret, SyncResult, UpdateStatus,
} from './types'

/** What the program answers when it refuses: a stable code and an English explanation. */
export class ApiError extends Error {
  readonly code: string

  constructor(code: string, message: string) {
    super(message)
    this.code = code
  }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const isFile = body instanceof Blob
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers: body === undefined || isFile ? undefined : { 'Content-Type': 'application/json' },
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
}

/** The most Jev calls the program lists at once. */
export const MOST_CALLS_LISTED = 1000
/** The most journal lines the program gives in one answer. */
const MOST_LINES_AT_ONCE = 1000

export const api = {
  authStatus: () => call<AuthStatus>('GET', '/auth/status'),
  startLogin: () => call<{ authorize_url: string }>('POST', '/auth/login/start'),
  loginWithCertificate: () => call<AuthStatus>('POST', '/auth/login/certificate'),
  finishLogin: (address: string) => call<AuthStatus>('POST', '/auth/login/finish', { address }),

  sagaFolder: () => call<{ saga_folder: string; demo?: boolean }>('GET', '/settings'),
  setSagaFolder: (saga_folder: string) => call<{ saga_folder: string }>('PUT', '/settings', { saga_folder }),
  /** `purpose` says which folder is being picked, so the dialog is titled for it and opens where that folder is. */
  chooseFolder: (purpose?: 'backups') =>
    call<{ folder: string | null }>('POST', `/settings/choose-folder${query({ purpose })}`),
  /** Opens the folder that invoice's SAGA file is really in, which may be an earlier SAGA folder. */
  openFolderOf: (invoiceId: string) => call('POST', '/folders/open', { invoice_id: invoiceId }),

  clients: () => call<{ clients: Client[] }>('GET', '/clients'),
  saveClient: (cui: string, name: string) => call('POST', '/clients', { cui, name }),
  setClientEnabled: (cui: string, enabled: boolean) =>
    call<{ clients: Client[] }>('PUT', `/clients/${cui}/enabled`, { enabled }),
  removeClient: (cui: string) => call('DELETE', `/clients/${cui}`),
  importClients: (file: File) =>
    call<ImportResult>('POST', `/clients/import${query({ filename: file.name })}`, file),

  sync: (cui: string, period: SyncPeriod) => call<SyncResult>('POST', '/sync', { cui, ...period }),

  receivedInvoices: (cui: string) =>
    call<{ invoices: Invoice[] }>('GET', `/invoices${query({ cui, type: 'primita' })}`),
  invoiceView: (id: string) => call<InvoiceView>('GET', `/invoices/${id}/view`),
  classify: (id: string, force = false) => call('POST', `/invoices/${id}/classify`, { force }),
  acceptSuggestion: (id: string) => call('POST', `/invoices/${id}/cont`, { accept: true }),
  setCont: (id: string, cont: string, force = false) => call('POST', `/invoices/${id}/cont`, { cont, force }),
  markUploaded: (ids: string[], uploaded = true) => call('POST', '/invoices/uploaded', { ids, uploaded }),

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
  saveAccount: (cont: string, description: string) => call('PUT', `/accounts/${cont}`, { description }),
  deleteAccount: (cont: string) => call('DELETE', `/accounts/${cont}`),
  setJevSettings: (settings: { min_confidence?: number; jev_instructions?: string }) =>
    call('PUT', '/classification/settings', settings),

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

  /** One operation is asked for as whole as the program gives it: it is read from its first step. */
  journal: (filter: JournalFilter, before?: number) =>
    call<{ events: JournalLine[]; has_more: boolean }>(
      'GET', `/events${query({ ...filter, before, limit: filter.trace ? MOST_LINES_AT_ONCE : undefined })}`,
    ),
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
