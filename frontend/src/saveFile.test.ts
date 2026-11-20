import { afterEach, describe, expect, it, vi } from 'vitest'
import { saveFile } from './saveFile'

/** A page that remembers the links pressed in it and the addresses made for files. */
function page() {
  const pressed: { href: string; download: string; inPage: boolean }[] = []
  const addresses = new Map<string, Blob>()
  let inPage = 0
  vi.stubGlobal('URL', {
    createObjectURL: (blob: Blob) => {
      const address = `blob:${addresses.size + 1}`
      addresses.set(address, blob)
      return address
    },
    revokeObjectURL: (address: string) => addresses.delete(address),
  })
  vi.stubGlobal('document', {
    createElement: () => {
      const link = { href: '', download: '', click: () => pressed.push({ href: link.href, download: link.download, inPage: inPage > 0 }), remove: () => { inPage -= 1 } }
      return link
    },
    body: { append: () => { inPage += 1 } },
  })
  return { pressed, addresses, linksLeft: () => inPage }
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('a file handed to the browser to save', () => {
  it('is saved under its own name, from a link pressed in the page', () => {
    const { pressed, addresses } = page()
    const file = new Blob(['<Facturi/>'], { type: 'application/xml' })

    saveFile(file, 'F_2816464_FV-1042_10.11.2026.xml')

    expect(pressed).toEqual([{ href: 'blob:1', download: 'F_2816464_FV-1042_10.11.2026.xml', inPage: true }])
    expect(addresses.get('blob:1')).toBe(file)
  })

  it('leaves nothing behind: the link at once, the address once the browser has started saving', () => {
    vi.useFakeTimers()
    const { addresses, linksLeft } = page()

    saveFile(new Blob(['<Facturi/>']), 'F.xml')

    expect(linksLeft()).toBe(0)
    expect(addresses.size).toBe(1) // still there for the browser to read
    vi.runAllTimers()
    expect(addresses.size).toBe(0)
  })
})
