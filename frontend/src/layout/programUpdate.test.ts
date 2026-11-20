import { describe, expect, it } from 'vitest'
import { shownVersion, updateOutcome, whatTheLookFound } from './programUpdate'
import type { UpdateStatus } from '../types'

const status = (last: UpdateStatus['last_update']): UpdateStatus => ({
  version: 'v0.1.1', installed_release: 'v0.1.1', latest_release: 'v0.2.0', update_available: true,
  can_update: true, why_not_kind: null, checked_at: null, check_error: null, last_update: last,
})
const earlier = { at: '2026-11-01T10:00:00+02:00', ok: true, from: 'v0.1.0', to: 'v0.1.1', error: null }

describe('the version on screen', () => {
  it('is the release without its v', () => {
    expect(shownVersion('v0.2.0')).toBe('0.2.0')
    expect(shownVersion('0.1.1')).toBe('0.1.1')
    expect(shownVersion(null)).toBe('')
  })
})

describe('what looking for a newer version found', () => {
  it('is said from the status the whole page shows, so it cannot contradict the notice on top', () => {
    expect(whatTheLookFound(status(null))).toBe('Există versiunea 0.2.0.')
    expect(whatTheLookFound({ ...status(null), latest_release: 'v0.1.1', update_available: false })).toBe('Aveți cea mai nouă versiune.')
  })

  it('says what a look found, for every kind of copy', () => {
    const copy = (over: Partial<UpdateStatus>): UpdateStatus => ({ ...status(null), update_available: false, ...over })
    expect(whatTheLookFound(copy({ latest_release: 'v0.3.0', installed_release: 'v0.3.0' }))).toBe('Aveți cea mai nouă versiune.')
    expect(whatTheLookFound(copy({ update_available: true, latest_release: 'v0.4.0' }))).toBe('Există versiunea 0.4.0.')
    expect(whatTheLookFound(copy({ can_update: false, why_not_kind: 'development', latest_release: 'v0.3.0' })))
      .toBe('Ultima versiune publicată este 0.3.0. O copie de dezvoltare se actualizează cu git, nu de aici.')
    expect(whatTheLookFound(copy({ can_update: false, why_not_kind: 'not_a_clone', latest_release: null })))
      .toBe('Această copie nu a fost instalată cu programul de instalare, așa că nu are de unde căuta.')
    expect(whatTheLookFound(copy({ can_update: false, why_not_kind: 'container', latest_release: null })))
      .toBe('Programul rulează pe NAS și se actualizează de acolo, cum scrie în README-NAS.md, nu de pe această pagină.')
    expect(whatTheLookFound(copy({ check_error: 'no network' }))).toBe('Nu am putut căuta. Verificați conexiunea la internet.')
  })

  it('says so when GitHub could not be asked', () => {
    expect(whatTheLookFound({ ...status(null), update_available: false, check_error: 'timed out' }))
      .toBe('Nu am putut căuta. Verificați conexiunea la internet.')
  })
})

describe('an update that was started', () => {
  it('is still working until the program writes how it ended', () => {
    expect(updateOutcome(null, undefined)).toBe('working') // the program is down, nothing answers
    expect(updateOutcome(null, status(null))).toBe('working')
    expect(updateOutcome(earlier.at, status(earlier))).toBe('working') // that is the update before this one
  })

  it('is done when a newer record says it worked', () => {
    const now = { at: '2026-11-14T10:00:00+02:00', ok: true, from: 'v0.1.1', to: 'v0.2.0', error: null }
    expect(updateOutcome(earlier.at, status(now))).toBe('done')
    expect(updateOutcome(null, status(now))).toBe('done')
  })

  it('has failed when a newer record says so', () => {
    const now = { at: '2026-11-14T10:00:00+02:00', ok: false, from: 'v0.1.1', to: 'v0.2.0', error: 'uv sync failed' }
    expect(updateOutcome(earlier.at, status(now))).toBe('failed')
  })
})
