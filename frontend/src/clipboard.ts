/** What to do when the browser would not copy, under a line that says what was not copied. */
export const COPY_REFUSED = 'Browserul nu a permis copierea. Încercați încă o dată, sau selectați textul și apăsați Ctrl+C.'

/**
 * Puts text on the clipboard, exactly as it is. Where the browser refuses the newer way, or has
 * none (a page that is not secure), the older copy command is tried; it fails only when both do.
 */
export async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
  } catch (refused) {
    if (!copyTheOlderWay(text)) throw refused
  }
}

/** The copy command, given the text itself rather than a selection, so that not even a line ending changes. */
function copyTheOlderWay(text: string): boolean {
  let given = false
  const give = (event: ClipboardEvent) => {
    if (!event.clipboardData) return
    event.clipboardData.setData('text/plain', text)
    event.preventDefault()
    given = true
  }
  document.addEventListener('copy', give)
  try {
    return document.execCommand('copy') && given
  } catch {
    return false
  } finally {
    document.removeEventListener('copy', give)
  }
}
