import type { InvoiceView, TrialAsk, TrialInvoice, TrialLine } from '../../types'

const BLANK_LINE: TrialLine = {
  description: '', quantity: '', unitPrice: '', sellerCode: '', barcode: '', commodityCodes: '', unit: null, vatPercent: null, value: null,
}

export const EMPTY: TrialInvoice = {
  clientCui: null, supplierName: '', supplierCui: '', currency: 'RON', creditNote: false, startedFrom: null, lines: [BLANK_LINE],
}

const line = (description: string, quantity: string, unitPrice: string): TrialLine => ({ ...BLANK_LINE, description, quantity, unitPrice })

export const EXAMPLES: { materiale: TrialInvoice; combustibil: TrialInvoice } = {
  materiale: {
    ...EMPTY, supplierName: 'Dedeman SRL', supplierCui: '2816464',
    lines: [line('Ciment Portland 40 kg', '20', '28,50'), line('Adeziv gresie flexibil 25 kg', '6', '41,00')],
  },
  combustibil: {
    ...EMPTY, supplierName: 'Rompetrol Downstream SRL', supplierCui: '1860712',
    lines: [line('Motorină Euro 5', '60', '7,25')],
  },
}

const blank = (value: string | null) => !value || value.trim() === ''
/**
 * A number as Romanians write it, with a decimal point, as the program reads it best. The spaces
 * between digits go ("12 000"); with a comma, the dots group thousands ("1.234,50"); without
 * one, a dot is the decimal point ("28.50"). The program reads them the same way.
 */
const number = (text: string) => {
  const compact = text.replace(/\s/g, '')
  return compact.includes(',') ? compact.replaceAll('.', '').replaceAll(',', '.') : compact
}
const orNull = (text: string) => (text.trim() === '' ? null : text.trim())

/**
 * What a refusal means on this screen: nearly always a number the program cannot read. The
 * other limits (50 rows, 500 characters in a text) are seldom reached by typing.
 */
export const REFUSED_HERE = { invalid_input: 'Cantitatea și prețul se scriu ca numere, de exemplu 20 și 28,50.' }

/** The JSON of `POST /rules/test`. Rows nothing was written on are left out. */
export function toRequest(trial: TrialInvoice, ask: TrialAsk) {
  const written = trial.lines.filter((row) => !(blank(row.description) && blank(row.quantity) && blank(row.unitPrice)))
  return {
    client_cui: trial.clientCui,
    supplier_name: trial.supplierName.trim(),
    supplier_cui: trial.supplierCui.trim(),
    currency: trial.currency,
    credit_note: trial.creditNote,
    ask,
    lines: written.map((row) => ({
      description: row.description.trim(),
      quantity: number(row.quantity),
      unit_price: number(row.unitPrice),
      seller_code: orNull(row.sellerCode),
      barcode: orNull(row.barcode),
      commodity_codes: row.commodityCodes.split(',').map((code) => code.trim()).filter(Boolean),
      unit: row.unit,
      vat_percent: row.vatPercent,
      value: row.value,
    })),
  }
}

/**
 * A trial invoice started from a saved one, so that sent unchanged it puts the question the
 * real invoice put. The codes are shown; the unit code, VAT rate, currency and each line's
 * value are kept without being shown. The value is kept because it is not always quantity ×
 * price (a line discount), and the largest value is what decides the line the rules read.
 */
export function fromDocument(view: InvoiceView): TrialInvoice {
  const document = view.document
  const lines = (document?.lines ?? []).map((row) => ({
    description: row.description,
    quantity: row.quantity.replace('.', ','),
    unitPrice: row.unit_price.replace('.', ','),
    sellerCode: row.seller_code ?? '',
    barcode: row.barcode ?? '',
    commodityCodes: row.commodity_codes.join(', '),
    unit: row.unit, // the code Jev was asked with (KGM), not the name SAGA shows (KG)
    vatPercent: row.vat_percent,
    value: row.value,
  }))
  return {
    clientCui: view.invoice.cui,
    supplierName: document?.supplier.name ?? '',
    supplierCui: document?.supplier.cui ?? '',
    currency: document?.currency || 'RON',
    creditNote: document?.is_credit_note ?? false,
    startedFrom: document?.number ?? null,
    lines: lines.length > 0 ? lines : EMPTY.lines,
  }
}

/** A row as changed by the person. A new quantity or price makes the carried value untrue. */
export function changeLine(line: TrialLine, changed: Partial<TrialLine>): TrialLine {
  const recomputed = 'quantity' in changed || 'unitPrice' in changed
  return { ...line, ...changed, ...(recomputed ? { value: null } : {}) }
}

/** Whether any row has a code, so the codes are shown without being asked for. */
export function hasCodes(trial: TrialInvoice): boolean {
  return trial.lines.some((row) => !blank(row.sellerCode) || !blank(row.barcode) || !blank(row.commodityCodes))
}

/** The form started again from an empty invoice or an example; the client chosen stays. */
export function startedFrom(start: 'empty' | 'materiale' | 'combustibil', clientCui: string | null): TrialInvoice {
  const base = start === 'empty' ? EMPTY : EXAMPLES[start]
  return { ...base, clientCui }
}
