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

describe('the technical side of the journal', () => {
  it('asks for the counts with the lines only when the technical view is on', async () => {
    const asked = program({ ok: true, events: [], has_more: false })
    await api.journal({ area: 'sync', technical: true })
    expect(asked[0].address).toBe('/api/events?area=sync&technical=true')
  })

  it('reads one operation\'s records a page at a time, and one record whole', async () => {
    const asked = program({ ok: true, records: [], has_more: false })
    await api.technical('a1b2c3')
    await api.technical('a1b2c3', 77)
    await api.technicalRecord(41)
    expect(asked.map((call) => call.address)).toEqual([
      '/api/events/technical?trace=a1b2c3&limit=2000',
      '/api/events/technical?trace=a1b2c3&before=77&limit=2000',
      '/api/events/technical/41',
    ])
  })

  it('puts the technical records in the saved file only when the view is on', () => {
    expect(api.journalFileAddress({ trace: 'a1', technical: true })).toBe('/api/events/export?trace=a1&technical=true&details=false')
  })
})

describe('the header the page sends in server mode', () => {
  it('goes with every call, a change or a file included', async () => {
    const headers: (Record<string, string> | undefined)[] = []
    vi.stubGlobal('fetch', async (_address: string, options?: { headers?: Record<string, string> }) => {
      headers.push(options?.headers)
      return new Response(JSON.stringify({ ok: true, events: [], has_more: false }))
    })
    await api.journal({ area: 'sync' })
    await api.setBackupFolder('/backups')
    await api.importClients(new File(['CUI\n12345674'], 'clienti.csv'))
    expect(headers.map((sent) => sent?.['X-AutoSaga-Page'])).toEqual(['1', '1', '1'])
  })
})

describe('a file waiting for SAGA, to save on this computer', () => {
  it('comes as the program has it, with the version of what was given', async () => {
    const asked: { address: string; header: string | undefined }[] = []
    vi.stubGlobal('fetch', async (address: string, options: { headers: Record<string, string> }) => {
      asked.push({ address, header: options.headers['X-AutoSaga-Page'] })
      return new Response('<?xml version="1.0"?><Facturi/>', {
        headers: { 'content-type': 'application/xml', 'X-AutoSaga-File-Version': '0123456789abcdef' },
      })
    })

    const { blob, version } = await api.sagaFile('12345674', 'F_1_A 1_09.11.2026.xml')

    expect(await blob.text()).toBe('<?xml version="1.0"?><Facturi/>')
    expect(version).toBe('0123456789abcdef')
    // Asked by the page itself, with its header: no link to it has to go without.
    expect(asked).toEqual([{ address: '/api/saga-files/12345674/files/F_1_A%201_09.11.2026.xml', header: '1' }])
  })

  it('has no version when the program did not say one', async () => {
    vi.stubGlobal('fetch', async () => new Response('<Facturi/>'))

    expect((await api.sagaFile('12345674', 'F.xml')).version).toBeNull()
  })

  it('says with the program\'s own code why it could not be given', async () => {
    vi.stubGlobal('fetch', async () =>
      new Response(JSON.stringify({ ok: false, error: { code: 'not_found', message: 'The file is gone.' } }), { status: 404 }))

    await expect(api.sagaFile('12345674', 'F.xml')).rejects.toMatchObject({ code: 'not_found' })
  })
})

describe('an import in SAGA confirmed on the page', () => {
  /** Answers every call and remembers what was sent. */
  function sent() {
    const bodies: unknown[] = []
    vi.stubGlobal('fetch', async (_: string, options: { body: string }) => {
      bodies.push(JSON.parse(options.body))
      return new Response(JSON.stringify({ ok: true, archive: null }))
    })
    return bodies
  }

  it('names the one file when a file is confirmed, with the version of that file as it was seen', async () => {
    const bodies = sent()
    await api.confirmSagaImport('12345674', 'aaaa', 'F_1_A1_09.11.2026.xml')
    expect(bodies).toEqual([{ version: 'aaaa', source: 'screen', file: 'F_1_A1_09.11.2026.xml' }])
  })

  it('names no file when all the client\'s files are confirmed', async () => {
    const bodies = sent()
    await api.confirmSagaImport('12345674', 'bbbb')
    expect(bodies).toEqual([{ version: 'bbbb', source: 'screen' }])
  })
})

describe('every client switched at once', () => {
  it('is one call, not one for each client, and says which way', async () => {
    const asked: { method: string; address: string; body: unknown }[] = []
    vi.stubGlobal('fetch', async (address: string, options: { method: string; body: string }) => {
      asked.push({ method: options.method, address, body: JSON.parse(options.body) })
      return new Response(JSON.stringify({ ok: true, clients: [] }))
    })
    await api.setAllClientsEnabled(false)
    await api.setAllClientsEnabled(true)
    expect(asked).toEqual([
      { method: 'PUT', address: '/api/clients/enabled', body: { enabled: false } },
      { method: 'PUT', address: '/api/clients/enabled', body: { enabled: true } },
    ])
  })
})
