import type { UpdateStatus } from '../types'

/** "0.2.0" from the release tag "v0.2.0". */
export function shownVersion(release: string | null): string {
  return (release ?? '').replace(/^v/, '')
}

export type UpdateOutcome = 'working' | 'done' | 'failed'

/**
 * How an update that was started has ended. The program writes a record when it finishes;
 * `recordBefore` is the time of the record that was there when the update began, so an
 * older update is not taken for this one. While the program is down nothing answers.
 */
export function updateOutcome(recordBefore: string | null, status: UpdateStatus | undefined): UpdateOutcome {
  const record = status?.last_update
  if (!record || record.at === recordBefore) return 'working'
  return record.ok ? 'done' : 'failed'
}
