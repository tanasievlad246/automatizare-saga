// The shapes the Python API returns. Field names are the API's own.

export type AuthStatus = {
  state: 'valid' | 'needs_refresh' | 'needs_login'
  refresh_expires_at: string | null
  refresh_days_left: number | null
  certificate_login?: boolean // the program can ask Windows for the certificate (only on Windows)
}

export type Client = {
  cui: string
  name: string
  invoices: number
  new_count: number
  review_count: number
  ready_count: number
  last_sync_at: string | null
  enabled: boolean
}

export type ClassificationStatus = 'pending' | 'classified' | 'review' | null

/** How the invoices waiting for SAGA are put in files: one file per client, or one per invoice. */
export type SagaFilePer = 'client' | 'invoice'

/** `show_issued`: whether a client's screen also lists the invoices the client issued. */
export type AppSettings = { saga_folder: string; saga_file_per: SagaFilePer; show_issued: boolean; demo?: boolean }

/** How one client's files for SAGA stand. `problem` is set while they could not be brought up to date. */
export type SagaState = {
  file_per: SagaFilePer
  written_at: string | null
  problem: { message: string; at: string } | null
}

export type Invoice = {
  id: string
  cui: string
  message_type: string
  invoice_number: string | null
  invoice_issue_date: string | null
  supplier_name: string | null
  customer_name: string | null
  currency: string | null
  total_payable: string | null
  uploaded_to_accounting: boolean
  is_new: boolean
  classification_status: ClassificationStatus
  cont: string | null
  classification_method: 'rules' | 'jev' | 'jev_accepted' | 'human' | null
  classification_reason: string | null
  suggested_cont: string | null
  confidence: number | null
  confidence_threshold: number | null
  saga_xml_path: string | null
  classification_error: string | null
  possible_duplicate_of: string | null
}

export type Party = {
  name: string | null
  cui: string | null
  vat_id: string | null
  city: string | null
  address: string | null
}

export type InvoiceLine = {
  number: number
  description: string
  seller_code: string | null
  barcode: string | null
  commodity_codes: string[] // CPV or NC
  unit: string | null // the unit code ANAF carries (KGM, H87); this is what Jev is asked with
  unit_name: string | null // the unit as SAGA shows it (KG, BUC)
  quantity: string
  unit_price: string
  value: string // without VAT; not always quantity × price (a line discount)
  vat_percent: string | null
}

export type InvoiceDocument = {
  number: string | null
  issue_date: string | null
  due_date: string | null
  currency: string | null
  is_credit_note: boolean
  supplier: Party
  customer: Party
  lines: InvoiceLine[]
  adjustments: { is_charge: boolean; reason: string | null; amount: string }[]
  total_without_vat: string | null
  total_vat: string | null
  total_payable: string | null
}

export type InvoiceView = {
  invoice: Invoice
  client_name: string | null
  document: InvoiceDocument | null
  xml: string | null
  saga_xml: string | null
  saga: SagaState
  jev: { probabilities: Record<string, number> | null; error: string | null } | null
  rule_suggestion: RuleSuggestion | null
}

/** A rule worth creating from one invoice that no rule decided. */
export type RuleSuggestion = {
  cont: string
  line: string // the invoice's largest line, where the words come from
  words: string[]
  ticked: string[] // the words to start with
  supplier_cui: string | null
  supplier_name: string | null
}

export type SyncResult = {
  window_days: number
  new_count: number // every message saved; of them, the invoices are counted in the next two
  received_count: number
  issued_count: number
  failed_count: number
  classification: { classified: number; review: number; pending: number } | null
}

export type ImportResult = {
  rows: number
  added: { cui: string; name: string }[]
  updated: { cui: string; name: string }[]
  unchanged: number
  rejected: { row: number; name: string; cui: string; code: string }[]
}

export type Rule = {
  id: number
  name: string
  cont: string
  keywords: string[]
  item_codes: string[]
  commodity_prefixes: string[]
  supplier_cuis: string[]
  client_cui: string | null
  enabled: boolean
}

export type RuleFields = Omit<Rule, 'id'>

export type RulesOverview = {
  accounts: Record<string, string>
  rules: Rule[]
  jev_instructions: string
  min_confidence: number
}

/** How a rule would have done on the invoices given an account lately. */
export type RuleEvidence = { matches: number; by_cont: Record<string, number> }

/** A rule worth creating, with the invoices behind it. It looks for words or for a supplier. */
export type ProposedRule = RuleEvidence & {
  cont: string
  keywords: string[]
  supplier_cuis: string[]
  supplier_name: string | null
  invoice_ids: string[]
}

export type ProposedRules = { count: number; days: number; suggestions: ProposedRule[] }

export type CostGroup = 'day' | 'week' | 'month' | 'year'

export type CostTotals = { calls: number; invoices: number; cost_usd: number }

export type Costs = CostTotals & {
  average_cost_per_invoice_usd: number | null
  by_period: (CostTotals & { period: string })[]
}

export type JevCall = {
  called_at: string
  message_id: string // "rule-test" for a question put by the rule test, not for an invoice
  cui: string | null // missing for a rule test with no client chosen
  client_name: string | null
  supplier_name: string | null
  invoice_number: string | null
  choice: string | null
  confidence: number | null
  classification_status: ClassificationStatus
  cost_usd: number | null
  error: string | null
}

export type Secret = { key: string; value: string; editable: boolean }

/** One copy of the database in the backup folder. */
export type Snapshot = { name: string; at: string; kind: 'auto' | 'manual' | 'before-restore'; size: number }

/** Where backups go, which ones are kept, and how the last attempts ended. */
export type BackupStatus = {
  folder: string | null
  folder_found: boolean
  snapshots: Snapshot[]
  count: number
  max: number
  last_at: string | null
  next_due_at: string | null
  due_now: boolean // true: the program makes one at its next look, within a quarter of an hour
  last_failure: { at: string; error: string } | null
  last_restore: { at: string; ok: boolean; name: string; error: string | null } | null
}

/** One line of the journal: something the program did. */
export type JournalLine = {
  id: number
  at: string
  level: 'detail' | 'info' | 'warning' | 'error'
  area: string
  event: string | null // a code the page can say in Romanian; null for a plain log line
  message: string // the program's own English line
  data: Record<string, unknown>
  trace: string | null // shared by every line of one operation
  duration_ms: number | null
}

/** Which release of the program is installed, and whether a newer one exists. */
export type UpdateStatus = {
  version: string
  installed_release: string | null
  latest_release: string | null
  update_available: boolean
  can_update: boolean // false for a copy the installer did not make
  why_not_kind: 'development' | 'not_a_clone' | null // why not, for the page to decide on
  checked_at: string | null
  check_error: string | null
  last_update: { at: string; ok: boolean; from: string | null; to: string; error: string | null } | null
}

/** One line of a trial invoice as the form holds it: everything typed, nothing converted yet. */
export type TrialLine = {
  description: string
  quantity: string
  unitPrice: string
  sellerCode: string
  barcode: string
  commodityCodes: string // typed with commas between the codes
  unit: string | null // carried from a saved invoice, not shown
  vatPercent: string | null // carried from a saved invoice, not shown
  value: string | null // carried from a saved invoice, not shown; dropped once quantity or price is changed
}

export type TrialInvoice = {
  clientCui: string | null
  supplierName: string
  supplierCui: string
  currency: string // carried from a saved invoice, not shown
  creditNote: boolean // carried from a saved invoice, not shown
  startedFrom: string | null // the number of the saved invoice the form started from
  lines: TrialLine[]
}

export type TrialAsk = 'rules_then_jev' | 'jev_only'

/** What Jev said about a trial invoice. `error` is the program's English line. */
export type TrialJev = {
  choice: string | null
  confidence: number | null
  threshold: number
  refused: boolean
  probabilities: Record<string, number>
  cost_usd: number | null
  duration_ms: number | null
  error: string | null
  http_status: number | null // what OpenRouter answered; null when it was not reached
}

export type RuleTestResult = {
  decided_by: 'rule' | 'jev' | 'nobody'
  cont: string | null
  account_description: string | null
  deciding_line: string | null
  rule: { name: string; line: number } | null
  jev: TrialJev | null // missing too when Jev failed because the request was too large to send
  why_not: 'no_lines' | 'no_key' | 'no_accounts' | 'jev_failed' | 'jev_declined' | 'below_threshold' | null
  reason: string // the program's English line
  suggestion: RuleSuggestion | null
}

/** One automatic download as the program recorded it. Moments are the PC's own time, without a zone. */
export type ScheduleRun = {
  slot: string; attempt: number; started_at: string; finished_at: string | null
  status: 'ok' | 'partial' | 'failed' | 'unreachable' | 'interrupted' | 'running'
  clients: number; failed_clients: number; new: number; review: number
  // Of the new messages, the received invoices and the ones the clients issued. Records
  // written before they were counted apart do not carry them; a failed run has none.
  received?: number | null; issued?: number | null
  error: { code: string; message: string } | null
  retry_at: string | null
  trace: string | null // the journal's number for this run's own lines
}
/** Which invoices an automatic download asks ANAF for: the last days, or the days between two dates (YYYY-MM-DD). */
export type SchedulePeriod = { days: number } | { start: string; end: string }
/** The automatic download: what was chosen, when it runs next, and how the last one went. */
export type ScheduleStatus = {
  enabled: boolean; days: number[]; times: string[]; period: SchedulePeriod; next_at: string | null
  running: { started_at: string; done: number; total: number } | null
  last_run: ScheduleRun | null
  clients_on: number; clients_off: number
}
