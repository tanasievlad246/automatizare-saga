/**
 * Hands a file to the browser to save under `name`, in the folder it saves downloads in: what a
 * link with `download` does, for a file the page has fetched itself.
 */
export function saveFile(file: Blob, name: string): void {
  const address = URL.createObjectURL(file)
  const link = document.createElement('a')
  link.href = address
  link.download = name
  document.body.append(link)
  link.click()
  link.remove()
  // Given back once the browser has started saving: at once, some browsers save nothing.
  setTimeout(() => URL.revokeObjectURL(address), 10_000)
}
