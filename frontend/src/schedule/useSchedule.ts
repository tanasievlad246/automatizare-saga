import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { api } from '../api'
import type { ScheduleStatus } from '../types'
import { pollEvery, runEnded } from './scheduleTexts'

/** The automatic download: asked often while it runs, rarely while it waits, never while it is off. */
export function useSchedule() {
  return useQuery({
    queryKey: ['schedule'],
    queryFn: api.schedule,
    refetchOnWindowFocus: true,
    refetchInterval: (query) => pollEvery(query.state.data),
  })
}

/** When an automatic download ends, even one the page did not watch, what it brought is read again. */
export function useRefreshWhenAutomaticDownloadEnds(): void {
  const queryClient = useQueryClient()
  const status = useSchedule().data
  const seen = useRef<ScheduleStatus | undefined>(undefined)
  useEffect(() => {
    if (runEnded(seen.current, status)) {
      for (const key of ['clients', 'invoices', 'proposed-rules', 'auth']) {
        void queryClient.invalidateQueries({ queryKey: [key] })
      }
    }
    if (status) seen.current = status
  }, [status, queryClient])
}
