import type { Sort } from './waitingFiles'

/** How the table of one file's invoices is seen: its order, its page, and the invoices that are open. */
export type TableState = { sort: Sort | null; page: number; open: string[] }

// How each table was last left, by client and file. Kept while the page is open, so the way back
// from an invoice ("‹ Facturile clientului") finds the table as it was, the invoice still open.
const tables = new Map<string, TableState>()

const asItStarts = (): TableState => ({ sort: null, page: 1, open: [] })

/** The table as it was last left; as it starts, when it was never changed. */
export function recallTable(key: string): TableState {
  const kept = tables.get(key)
  return kept ? { ...kept, open: [...kept.open] } : asItStarts()
}

/** Notes how a table is seen now. One that is as it starts is not kept. */
export function rememberTable(key: string, state: TableState): void {
  if (state.sort === null && state.page === 1 && state.open.length === 0) tables.delete(key)
  else tables.set(key, { ...state, open: [...state.open] })
}
