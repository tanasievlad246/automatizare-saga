// Every call the page makes to the Python program, in one place.

import type {
  AuthStatus, Client, CostGroup, Costs, ImportResult, Invoice, InvoiceView, JevCall, ProposedRules,
  RuleEvidence, RuleFields, RulesOverview, Secret, SyncResult,
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
/** The most Jev calls the program lists at once. */
export const MOST_CALLS_LISTED = 1000

export const api = {
  authStatus: () => call<AuthStatus>('GET', '/auth/status'),
  startLogin: () => call<{ authorize_url: string }>('POST', '/auth/login/start'),
  finishLogin: (address: string) => call<AuthStatus>('POST', '/auth/login/finish', { address }),

  sagaFolder: () => call<{ saga_folder: string }>('GET', '/settings'),
  setSagaFolder: (saga_folder: string) => call<{ saga_folder: string }>('PUT', '/settings', { saga_folder }),
  chooseFolder: () => call<{ folder: string | null }>('POST', '/settings/choose-folder'),
  /** Opens the folder that invoice's SAGA file is really in, which may be an earlier SAGA folder. */
  openFolderOf: (invoiceId: string) => call('POST', '/folders/open', { invoice_id: invoiceId }),

  clients: () => call<{ clients: Client[] }>('GET', '/clients'),
  saveClient: (cui: string, name: string) => call('POST', '/clients', { cui, name }),
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

  secrets: () => call<{ secrets: Secret[] }>('GET', '/secrets'),
  setSecret: (key: string, value: string) => call('PUT', `/secrets/${key}`, { value }),
}
