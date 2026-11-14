import { describe, expect, it } from 'vitest'
import { ApiError } from '../api'
import { isWaitingFor, nextView, openingView } from './certificateLogin'
import type { LoginView } from './certificateLogin'

const refused = new ApiError('login_refused', 'ANAF refused the login: access_denied')
const waiting = (attempt = 1): LoginView => ({ kind: 'waiting', attempt })

describe('what the ANAF login window shows', () => {
  it('opens on the certificate way where the program offers it', () => {
    expect(openingView(true)).toEqual({ kind: 'certificate' })
  })

  it('opens on the three browser steps where it is not offered, or not known yet', () => {
    expect(openingView(false)).toEqual({ kind: 'browser' })
    expect(openingView(undefined)).toEqual({ kind: 'browser' })
  })

  it('waits once the certificate button, or "Încearcă din nou", is pressed', () => {
    expect(nextView({ kind: 'certificate' }, { type: 'ask', attempt: 1 })).toEqual(waiting(1))
    expect(nextView({ kind: 'failed', error: refused }, { type: 'ask', attempt: 2 })).toEqual(waiting(2))
  })

  it('goes back to the certificate way, with a sentence, when no certificate was chosen', () => {
    const cancelled = new ApiError('login_cancelled', 'No certificate was chosen.')

    expect(nextView(waiting(1), { type: 'failed', attempt: 1, error: cancelled })).toEqual({
      kind: 'certificate', note: 'Nu a fost ales niciun certificat.',
    })
  })

  it('shows the failure, holding the error, for any other answer', () => {
    expect(nextView(waiting(1), { type: 'failed', attempt: 1, error: refused })).toEqual({ kind: 'failed', error: refused })
    const other = new Error('boom')
    expect(nextView(waiting(1), { type: 'failed', attempt: 1, error: other })).toEqual({ kind: 'failed', error: other })
  })

  it('goes back to the certificate way when the person gives up waiting', () => {
    expect(nextView(waiting(1), { type: 'giveUp' })).toEqual({ kind: 'certificate' })
  })

  it('does not change for a failure that comes after the person gave up', () => {
    const gaveUp = nextView(waiting(1), { type: 'giveUp' })

    expect(isWaitingFor(gaveUp, 1)).toBe(false)
    expect(nextView(gaveUp, { type: 'failed', attempt: 1, error: refused })).toBe(gaveUp)
  })

  it('does not take an old attempt\'s answer for the new one', () => {
    const second = nextView(nextView(waiting(1), { type: 'giveUp' }), { type: 'ask', attempt: 2 })

    expect(isWaitingFor(second, 1)).toBe(false)
    expect(isWaitingFor(second, 2)).toBe(true)
    expect(nextView(second, { type: 'failed', attempt: 1, error: refused })).toBe(second)
  })

  it('shows the browser steps when "Conectare prin browser" is pressed, from anywhere', () => {
    for (const view of [{ kind: 'certificate' }, { kind: 'failed', error: refused }] as LoginView[]) {
      expect(nextView(view, { type: 'browser' })).toEqual({ kind: 'browser' })
    }
  })
})
