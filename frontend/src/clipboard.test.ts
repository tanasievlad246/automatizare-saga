import { afterEach, describe, expect, it, vi } from 'vitest'
import { copyText } from './clipboard'

/** A page where the newer way to copy works or is refused, and the older way works or not. */
function page({ newer, older }: { newer: boolean; older: boolean }) {
  const pasted: string[] = []
  const listeners = new Set<(event: ClipboardEvent) => void>()
  vi.stubGlobal('navigator', {
    clipboard: {
      writeText: async (text: string) => {
        if (!newer) throw new DOMException('Write permission denied.', 'NotAllowedError')
        pasted.push(text)
      },
    },
  })
  vi.stubGlobal('document', {
    addEventListener: (_: string, listener: (event: ClipboardEvent) => void) => listeners.add(listener),
    removeEventListener: (_: string, listener: (event: ClipboardEvent) => void) => listeners.delete(listener),
    execCommand: () => {
      if (!older) return false
      const data = new Map<string, string>()
      for (const listener of listeners) listener({ clipboardData: { setData: (kind: string, text: string) => data.set(kind, text) }, preventDefault: () => {} } as unknown as ClipboardEvent)
      pasted.push(data.get('text/plain') ?? '')
      return true
    },
  })
  return { pasted, listeners }
}

const XML = '<?xml version="1.0"?>\r\n<Invoice><cbc:Note>Două  spații</cbc:Note></Invoice>'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('copying text', () => {
  it('copies it exactly as it is', async () => {
    const { pasted } = page({ newer: true, older: false })

    await copyText(XML)

    expect(pasted).toEqual([XML])
  })

  it('copies it the older way, still exactly, when the browser refuses the newer one', async () => {
    const { pasted, listeners } = page({ newer: false, older: true })

    await copyText(XML)

    expect(pasted).toEqual([XML])
    expect(listeners.size).toBe(0)
  })

  it('fails when the browser refuses both', async () => {
    const { pasted, listeners } = page({ newer: false, older: false })

    await expect(copyText(XML)).rejects.toThrow('Write permission denied.')
    expect(pasted).toEqual([])
    expect(listeners.size).toBe(0)
  })

  it('tries the older way where there is no clipboard at all, as on a page that is not secure', async () => {
    const { pasted } = page({ newer: false, older: true })
    vi.stubGlobal('navigator', {})

    await copyText(XML)

    expect(pasted).toEqual([XML])
  })
})
