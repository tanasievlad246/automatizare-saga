// The shapes the Python API returns. Field names are the API's own.

export type AuthStatus = {
  state: 'valid' | 'needs_refresh' | 'needs_login'
  refresh_expires_at: string | null
  refresh_days_left: number | null
}

export type Client = {
  cui: string
  name: string
  invoices: number
  new_count: number
  review_count: number
  ready_count: number
  last_sync_at: string | null
}

export type ClassificationStatus = 'pending' | 'classified' | 'review' | null

export type Invoice = {
  id: string
  cui: string
  message_type: string
  invoice_number: string | null
  invoice_issue_date: string | null
  supplier_name: string | null
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
  unit_name: string | null
  quantity: string
  unit_price: string
  value: string
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
  new_count: number
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
  message_id: string
  cui: string
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
