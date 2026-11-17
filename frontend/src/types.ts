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
  per_line: boolean // each line of its invoices gets its own account
  invoices: number // received ones
  issued_count: number // the ones it issued itself
  new_count: number // received ones
  issued_new_count: number
  review_count: number // of both kinds
  issued_review_count: number
  ready_count: number // of both kinds
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
  supplier_cui: string | null
  customer_name: string | null
  customer_cui: string | null
  currency: string | null
  total_with_vat: string | null // what the invoice is worth: this is the "Total" of every list
  total_payable: string | null // what is left to pay: more with an earlier balance, less with an advance
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
  line_accounts: LineAccount[] | null // null: one account for the whole invoice
  classification_error: string | null
  possible_duplicate_of: string | null
}

/** The account of one line of an invoice decided line by line. `line` is its number on the invoice. */
export type LineAccount = {
  line: number
  cont: string | null // null while it waits for a person
  method: 'rules' | 'jev' | 'jev_accepted' | 'human' | 'follows' | null // follows: the largest line's account
  rule: string | null
  reason: string // the program's English explanation
  suggested_cont: string | null
  confidence: number | null
  confidence_threshold: number | null
  probabilities: Record<string, number> | null // how likely Jev found each account, for this line
  asked: boolean // Jev was asked about this line
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
  total_with_vat: string | null
  total_prepaid: string | null // paid before; negative when the supplier adds an earlier unpaid balance
  total_rounding: string | null
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
  from_line?: number // in "Testează regulile": the number of the line the words come from
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
  direction: InvoiceKind // the invoices it decides
}

export type RuleFields = Omit<Rule, 'id'>

/** Received by the client, or issued by it: each kind has its own accounts, rules and questions. */
export type InvoiceKind = 'received' | 'issued'

export type RulesOverview = {
  accounts: Record<string, string>
  issued_accounts: Record<string, string> // for the invoices a client issued
  rules: Rule[]
  jev_instructions: string // the question about a whole invoice
  jev_line_instructions: string // the question about one line
  jev_issued_instructions: string // the same two, for the invoices a client issued
  jev_issued_line_instructions: string
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
  customer_name: string | null // for an invoice the client issued
  message_type: string | null
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
  // What left the program: the question, and the invoice or line it was about, as sent.
  sent: { question: string; state: JevState }
}

/** What Jev is told about a trial invoice (`linii`) or about one of its lines (`linia`). */
export type JevState = {
  furnizor?: { nume: string | null; cui: string | null } // null when the trial left them blank
  factura: { tip: string; moneda: string; total_fara_tva?: string | null }
  linia?: JevLine
  linii?: JevLine[]
  linia_cu_valoarea_cea_mai_mare?: number | null
  linii_omise?: number
}
export type JevLine = {
  nr: number; descriere: string; cod_furnizor?: string; coduri_clasificare?: string[]; um?: string
  cantitate?: string; valoare_fara_tva?: string; cota_tva?: string
}

/** The rule that decided, which of its conditions the line meets, and what else would have matched. */
export type TrialRule = {
  name: string
  line: number
  condition: 'supplier_cui' | 'seller_code' | 'barcode' | 'commodity_code' | 'keyword' | null
  found: string | null // the CUI, the code on the line, or the keyword as the rule has it
  prefix: string | null // for a classification code: the start the rule names
  client_only: boolean
  also: string[] // rules further down the list that match too
}

export type TrialWhyNot =
  | 'no_lines' | 'no_key' | 'no_accounts' | 'jev_failed' | 'jev_declined' | 'below_threshold'
  | 'lines_left' // line by line: the largest line has its account, another line waits
  | 'not_asked' // line by line: not sent, as OpenRouter failed as a whole on an earlier line
  | null

/** One line of the trial invoice, and how it was decided. */
export type TrialLineAnswer = {
  line: number
  description: string
  value: string
  decided_by: 'rule' | 'jev' | 'follows' | 'nobody'
  cont: string | null
  account_description: string | null
  rule: TrialRule | null
  jev: TrialJev | null // missing too when Jev failed because the request was too large to send
  why_not: TrialWhyNot
  reason: string // the program's English line
  follows: number | null // the largest line, whose account a discount takes
  same_as: number | null // the earlier line that says the same; Jev was asked once, about that one
}

export type RuleTestResult = {
  per_line: boolean // each line on its own; otherwise one account, by the largest line
  lines: TrialLineAnswer[] // every line; for one account per invoice, only the line that decides
  // The invoice as the program keeps it: line by line, the largest line's, with an account
  // only once every line has one.
  decided_by: 'rule' | 'jev' | 'nobody'
  cont: string | null
  account_description: string | null
  deciding_line: string | null
  rule: TrialRule | null
  jev: TrialJev | null
  why_not: TrialWhyNot
  reason: string // the program's English line
  waiting?: number // line by line: how many lines have no account
  accounts: Record<string, string> // what Jev chose from: account -> what belongs on it
  jev_calls: number
  cost_usd: number | null
  // OpenRouter failed as a whole (key, credit, rate limit, no connection) and nothing more was sent.
  jev_stopped?: { line: number; http_status: number | null; error: string } | null
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
