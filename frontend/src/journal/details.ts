/** A detail of a journal line as text: an object or a list as JSON, anything else as it is. */
export function detailText(value: unknown): string {
  return typeof value === 'object' && value !== null ? JSON.stringify(value) : String(value)
}
