import { describe, expect, it } from 'vitest'
import { describeAnafConnection } from './anafConnection'
import type { AuthStatus } from '../types'

const status = (days: number | null, state: AuthStatus['state'] = 'valid'): AuthStatus => ({
  state, refresh_expires_at: '2027-06-14T10:00:00+03:00', refresh_days_left: days,
})

describe('the ANAF connection in the top bar', () => {
  it('says it is still checking before the program has answered', () => {
    expect(describeAnafConnection(undefined, false)).toMatchObject({
      state: 'checking', label: 'Se verifică conectarea la ANAF…',
    })
  })

  it('says the program is silent instead of asking for a login', () => {
    expect(describeAnafConnection(undefined, true)).toMatchObject({ state: 'unreachable', label: 'Programul nu răspunde' })
  })

  it('shows the days left while there are plenty', () => {
    expect(describeAnafConnection(status(342), false)).toEqual({
      state: 'connected',
      label: 'Conectat la ANAF · încă 342 de zile',
      hint: 'Valabilă până la 14.06.2027. Apoi este nevoie din nou de tokenul USB și de PIN.',
    })
    expect(describeAnafConnection(status(31, 'needs_refresh'), false).state).toBe('connected')
  })

  it('warns from thirty days before the end', () => {
    expect(describeAnafConnection(status(30), false)).toMatchObject({
      state: 'expiring', label: 'Conectarea la ANAF expiră în 30 de zile',
    })
    expect(describeAnafConnection(status(12), false).label).toBe('Conectarea la ANAF expiră în 12 zile')
    expect(describeAnafConnection(status(1), false).label).toBe('Conectarea la ANAF expiră mâine')
    expect(describeAnafConnection(status(0), false).label).toBe('Conectarea la ANAF expiră azi')
  })

  it('asks for a login when there is none', () => {
    expect(describeAnafConnection(status(null, 'needs_login'), false)).toMatchObject({
      state: 'disconnected', label: 'Neconectat la ANAF · Conectați-vă',
    })
  })
})
