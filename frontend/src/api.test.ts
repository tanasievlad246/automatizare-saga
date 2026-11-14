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
