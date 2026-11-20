import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'

/** Answers every call with `reply` and remembers what was asked for. */
function program(reply: object = { ok: true }) {
  const asked: { method: string; address: string }[] = []
  vi.stubGlobal('fetch', async (address: string, options: { method: string }) => {
    asked.push({ method: options.method, address })
    return new Response(JSON.stringify(reply))
  })
  return asked
}

afterEach(() => vi.unstubAllGlobals())

describe('the journal as the page asks for it', () => {
  it('asks for one operation as whole as the program gives it', async () => {
    const asked = program({ ok: true, events: [], has_more: false })
    await api.journal({ trace: 'a1b2c3' })
    await api.journal({ trace: 'a1b2c3' }, 4200)
    expect(asked.map((call) => call.address)).toEqual([
      '/api/events?trace=a1b2c3&limit=1000',
      '/api/events?trace=a1b2c3&before=4200&limit=1000',
    ])
  })

  it('leaves the number of lines to the program everywhere else', async () => {
    const asked = program({ ok: true, events: [], has_more: false })
    await api.journal({ area: 'sync' })
    expect(asked[0].address).toBe('/api/events?area=sync')
  })
})

describe('the journal saved as a file', () => {
  it('has the details only when the page shows them', () => {
    // Said even when it is "no": the program adds the details unless told otherwise.
    expect(api.journalFileAddress({ area: 'sync' })).toBe('/api/events/export?area=sync&details=false')
    expect(api.journalFileAddress({ area: 'sync', details: false })).toBe('/api/events/export?area=sync&details=false')
    expect(api.journalFileAddress({ area: 'sync', details: true })).toBe('/api/events/export?area=sync&details=true')
  })
})

describe('choosing a folder in Windows’ own dialog', () => {
  it('says when the folder is for the copies', async () => {
    const asked = program({ ok: true, folder: null })
    await api.chooseFolder('backups')
    await api.chooseFolder()
    expect(asked).toEqual([
      { method: 'POST', address: '/api/settings/choose-folder?purpose=backups' },
      { method: 'POST', address: '/api/settings/choose-folder' },
    ])
  })
})

describe('a file waiting for SAGA, read as it is in the folder', () => {
  it('is asked for by its client and its name, and comes as text', async () => {
    const asked: string[] = []
    vi.stubGlobal('fetch', async (address: string) => {
      asked.push(address)
      return new Response('<?xml version="1.0"?><Facturi/>', { headers: { 'content-type': 'application/xml' } })
    })

    expect(await api.sagaFileXml('12345674', 'F_1_A&B 1_09.11.2026.xml')).toBe('<?xml version="1.0"?><Facturi/>')
    expect(asked).toEqual(['/api/saga-files/12345674/files/F_1_A%26B%201_09.11.2026.xml'])
  })

  it('says with the program\'s own code why it could not be read', async () => {
    vi.stubGlobal('fetch', async () =>
      new Response(JSON.stringify({ ok: false, error: { code: 'not_found', message: 'The file is gone from the client\'s folder.' } }), { status: 404 }))

    await expect(api.sagaFileXml('12345674', 'F.xml')).rejects.toMatchObject({ code: 'not_found' })
  })

  it('says the program did not answer when it did not', async () => {
    vi.stubGlobal('fetch', async () => {
      throw new TypeError('Failed to fetch')
    })

    await expect(api.sagaFileXml('12345674', 'F.xml')).rejects.toMatchObject({ code: 'unreachable' })
  })
})
