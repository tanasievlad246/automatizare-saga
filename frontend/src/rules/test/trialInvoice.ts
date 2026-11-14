import type { InvoiceView, TrialAsk, TrialInvoice, TrialLine } from '../../types'

const BLANK_LINE: TrialLine = {
  description: '', quantity: '', unitPrice: '', sellerCode: '', barcode: '', commodityCodes: '', unit: null, vatPercent: null,
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
// The program reads a point as the decimal separator; the person types a comma.
const number = (text: string) => text.trim().replace(',', '.')
const orNull = (text: string) => (text.trim() === '' ? null : text.trim())

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
    })),
  }
}

/**
 * A trial invoice started from a saved one. The page's copy of an invoice has no codes on its
 * lines, so those stay blank. The unit, VAT rate and currency are kept, so Jev is asked what
 * it was asked for that invoice.
 */
export function fromDocument(view: InvoiceView): TrialInvoice {
  const document = view.document
  return {
    clientCui: view.invoice.cui,
    supplierName: document?.supplier.name ?? '',
    supplierCui: document?.supplier.cui ?? '',
    currency: document?.currency || 'RON',
    creditNote: document?.is_credit_note ?? false,
    startedFrom: document?.number ?? null,
    lines: (document?.lines ?? []).map((row) => ({
      ...BLANK_LINE,
      description: row.description,
      quantity: row.quantity,
      unitPrice: row.unit_price.replace('.', ','),
      unit: row.unit_name,
      vatPercent: row.vat_percent,
    })),
  }
}

/** The form started again from an empty invoice or an example; the client chosen stays. */
export function startedFrom(start: 'empty' | 'materiale' | 'combustibil', clientCui: string | null): TrialInvoice {
  const base = start === 'empty' ? EMPTY : EXAMPLES[start]
  return { ...base, clientCui }
}
