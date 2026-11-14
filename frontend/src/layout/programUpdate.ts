import type { UpdateStatus } from '../types'
import { jobOutcome } from './useRestartingJob'

/** "0.2.0" from the release tag "v0.2.0". */
export function shownVersion(release: string | null): string {
  return (release ?? '').replace(/^v/, '')
}

export const COULD_NOT_LOOK = 'Nu am putut căuta. Verificați conexiunea la internet.'

/** What looking for a newer release found, as the foot of the menu says it. */
export function whatTheLookFound(status: UpdateStatus): string {
  if (status.check_error) return COULD_NOT_LOOK
  return status.update_available ? `Există versiunea ${shownVersion(status.latest_release)}.` : 'Aveți cea mai nouă versiune.'
}

/** How an update that was started has ended; see jobOutcome. */
export function updateOutcome(recordBefore: string | null, status: UpdateStatus | undefined) {
  return jobOutcome(recordBefore, status?.last_update)
}
