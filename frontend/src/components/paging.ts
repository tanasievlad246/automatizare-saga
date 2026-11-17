/** One page of a list: its rows, which page it is of how many, and the rows' numbers in the whole list. */
export type Page<T> = { items: T[]; page: number; pages: number; first: number; last: number; total: number }

/**
 * The rows of one page. A page past the end gives the last one: when the last row of a page
 * leaves the list (an invoice that got its account leaves "De verificat"), the page before it shows.
 */
export function pageOf<T>(items: T[], wanted: number, size: number): Page<T> {
  const total = items.length
  const pages = Math.max(1, Math.ceil(total / size))
  const page = Math.min(Math.max(1, wanted), pages)
  const start = (page - 1) * size
  const shown = items.slice(start, start + size)
  return { items: shown, page, pages, first: shown.length ? start + 1 : 0, last: start + shown.length, total }
}

/**
 * The page numbers under a list, `null` standing for a gap ("…"): all of them when there are
 * at most seven; otherwise the first, the last, and the ones around the page shown.
 */
export function pageNumbers(page: number, pages: number): (number | null)[] {
  if (pages <= 7) return Array.from({ length: pages }, (_, index) => index + 1)
  const kept = new Set([1, pages, page - 1, page, page + 1])
  if (page <= 2) [2, 3].forEach((each) => kept.add(each))
  if (page >= pages - 1) [pages - 2, pages - 1].forEach((each) => kept.add(each))
  const sorted = [...kept].filter((each) => each >= 1 && each <= pages).sort((one, other) => one - other)
  const numbers: (number | null)[] = []
  for (const each of sorted) {
    const before = numbers.at(-1)
    // A gap that would hide only one page shows that page instead.
    if (typeof before === 'number' && each - before === 2) numbers.push(before + 1)
    else if (typeof before === 'number' && each - before > 2) numbers.push(null)
    numbers.push(each)
  }
  return numbers
}

/** The page written in the address ("?pagina=3"); anything that is not a whole number from 1 up is the first. */
export function pageFrom(text: string | null): number {
  return text && /^[1-9]\d*$/.test(text) ? Number(text) : 1
}

/** Beside the page numbers: "Facturile 26–50 din 312", "Factura 26 din 26", "Clienții 1–20 din 31 găsiți". */
export function rangeLine(page: Page<unknown>, noun: { one: string; many: string }, found?: string): string {
  const of = `din ${page.total}${found ? ` ${found}` : ''}`
  return page.first === page.last ? `${noun.one} ${page.first} ${of}` : `${noun.many} ${page.first}–${page.last} ${of}`
}
