import { countOf, formatDate } from '../format'
import type { AuthStatus } from '../types'

/** From how many days before the end the top bar starts to warn. */
export const WARN_DAYS_BEFORE = 30

export type AnafConnection = {
  state: 'checking' | 'unreachable' | 'connected' | 'expiring' | 'disconnected'
  label: string
  hint: string // shown when the pointer rests on it
}

/**
 * What the top bar says about the ANAF login. "Not answered yet" and "the program is
 * stopped" are states of their own: neither is a reason to ask the person to log in.
 */
export function describeAnafConnection(status: AuthStatus | undefined, failed: boolean): AnafConnection {
  if (failed) return { state: 'unreachable', label: 'Programul nu răspunde', hint: 'Porniți AutoSaga de pe Desktop.' }
  if (!status) return { state: 'checking', label: 'Se verifică conectarea la ANAF…', hint: '' }
  if (status.state === 'needs_login') {
    return {
      state: 'disconnected',
      label: 'Neconectat la ANAF · Conectați-vă',
      hint: 'Fără conectare nu se pot descărca facturi.',
    }
  }
  const days = status.refresh_days_left ?? 0
  if (days <= WARN_DAYS_BEFORE) {
    const when = days === 0 ? 'azi' : days === 1 ? 'mâine' : `în ${countOf(days, 'o zi', 'zile')}`
    return {
      state: 'expiring',
      label: `Conectarea la ANAF expiră ${when}`,
      hint: 'Pregătiți tokenul USB și PIN-ul, apoi apăsați aici.',
    }
  }
  return {
    state: 'connected',
    label: `Conectat la ANAF · încă ${countOf(days, 'o zi', 'zile')}`,
    hint: `Valabilă până la ${formatDate(status.refresh_expires_at)}. Apoi este nevoie din nou de tokenul USB și de PIN.`,
  }
}
