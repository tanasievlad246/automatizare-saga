import { describe, expect, it } from 'vitest'
import { startAfterReading } from './useRestartingJob'

type Status = { last: { at: string; ok: boolean; error: string | null } | null }
const earlier = { at: '2026-11-01T10:00:00+02:00', ok: true, error: null }

describe('starting a job that restarts the program', () => {
  it('reads the record that is there first, from the program itself, then starts', async () => {
    const steps: string[] = []
    const before = await startAfterReading<Status>({
      read: async () => {
        steps.push('read')
        return { last: earlier }
      },
      start: async () => {
        steps.push('start')
      },
      recordOf: (status) => status?.last,
    })
    expect(steps).toEqual(['read', 'start'])
    expect(before).toBe(earlier.at)
  })

  it('remembers that there was no record', async () => {
    const before = await startAfterReading<Status>({
      read: async () => ({ last: null }),
      start: async () => {},
      recordOf: (status) => status?.last,
    })
    expect(before).toBeNull()
  })

  it('starts nothing when the program cannot be read', async () => {
    let started = false
    const begun = startAfterReading<Status>({
      read: async () => {
        throw new Error('The program did not answer.')
      },
      start: async () => {
        started = true
      },
      recordOf: (status) => status?.last,
    })
    await expect(begun).rejects.toThrow('The program did not answer.')
    expect(started).toBe(false)
  })
})
