import { useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

const ASK_AGAIN_EVERY = 2000 // milliseconds between looks, while the program is away
// After this the window says it is taking long and may be closed. A restore is long over by
// then; an update on a slow connection may still be running, so the asking goes on.
const TOO_LONG = 3 * 60_000

/** What the program writes when such a job ends. */
export type JobRecord = { at: string; ok: boolean; error: string | null } | null | undefined
export type JobPhase = 'asking' | 'working' | 'done' | 'failed' | 'slow'

/**
 * How a job that was started has ended. The program writes a record when it finishes;
 * `recordBefore` is the time of the record that was there when the job began, so an older
 * run is not taken for this one. While the program is down nothing answers.
 */
export function jobOutcome(recordBefore: string | null, record: JobRecord): 'working' | 'done' | 'failed' {
  if (!record || record.at === recordBefore) return 'working'
  return record.ok ? 'done' : 'failed'
}

type Job<Status> = {
  start: () => Promise<unknown>
  read: () => Promise<Status>
  recordOf: (status: Status | undefined) => JobRecord
}

/**
 * Starts the job and answers with the time of the record that was there just before it.
 * That record is read from the program at this moment, not taken from what the page already
 * holds: a page left open can hold an old answer, and a run made since then would be taken
 * for the end of this one.
 */
export async function startAfterReading<Status>({ start, read, recordOf }: Job<Status>): Promise<string | null> {
  const before = recordOf(await read())?.at ?? null
  await start()
  return before
}

/**
 * A job that stops the program and starts it again (an update, a restore). The page starts
 * it, then keeps asking how it ended: for a while nothing answers, which is expected.
 */
export function useRestartingJob<Status>({ name, start, read, recordOf }: Job<Status> & { name: string }) {
  const begin = useMutation({ mutationFn: () => startAfterReading({ start, read, recordOf }) })
  const latest = useQuery({
    queryKey: [name, 'while-working'],
    queryFn: read,
    enabled: begin.isSuccess,
    refetchInterval: ASK_AGAIN_EVERY,
    // Also while the page is behind another tab or window: the result must be there on return.
    refetchIntervalInBackground: true,
    retry: false, // it fails on purpose while the program is stopped
    gcTime: 0,
  }).data
  const [tookTooLong, setTookTooLong] = useState(false)
  useEffect(() => {
    if (!begin.isSuccess) return
    const timer = window.setTimeout(() => setTookTooLong(true), TOO_LONG)
    return () => window.clearTimeout(timer)
  }, [begin.isSuccess])

  const record = recordOf(latest)
  const outcome = begin.isSuccess ? jobOutcome(begin.data, record) : 'working'
  const phase: JobPhase = begin.isError
    ? 'failed'
    : !begin.isPending && !begin.isSuccess
      ? 'asking'
      : outcome === 'working' ? (tookTooLong ? 'slow' : 'working') : outcome
  return { phase, begin: () => begin.mutate(), startError: begin.error, record }
}
