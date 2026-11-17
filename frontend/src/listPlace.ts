// Where each list was last left: its page, search and filters, as the address held them. Kept while the
// page is open, so a link back ("‹ Toți clienții", "‹ Facturile clientului") returns there, not to the start.
const places = new Map<string, string>()

/** Notes how a list is seen now; `search` is its address after the "?", empty for the bare list. */
export function rememberPlace(path: string, search: string): void {
  if (search) places.set(path, search)
  else places.delete(path)
}

/** The link back to a list, as it was last seen. */
export function placeOf(path: string): string {
  const search = places.get(path)
  return search ? `${path}?${search}` : path
}
