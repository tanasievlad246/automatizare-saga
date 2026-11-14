import { describe, expect, it } from 'vitest'
import { shownVersion, updateOutcome } from './programUpdate'
import type { UpdateStatus } from '../types'

const status = (last: UpdateStatus['last_update']): UpdateStatus => ({
  version: 'v0.1.1', installed_release: 'v0.1.1', latest_release: 'v0.2.0', update_available: true,
  can_update: true, checked_at: null, check_error: null, last_update: last,
})
const earlier = { at: '2026-11-01T10:00:00+02:00', ok: true, from: 'v0.1.0', to: 'v0.1.1', error: null }

describe('the version on screen', () => {
  it('is the release without its v', () => {
    expect(shownVersion('v0.2.0')).toBe('0.2.0')
    expect(shownVersion('0.1.1')).toBe('0.1.1')
    expect(shownVersion(null)).toBe('')
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
