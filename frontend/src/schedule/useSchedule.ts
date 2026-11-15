import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { api } from '../api'
import { pollEvery } from './scheduleTexts'

/** The automatic download: asked often while it runs, rarely while it waits, never while it is off. */
export function useSchedule() {
  return useQuery({
    queryKey: ['schedule'],
    queryFn: api.schedule,
    refetchOnWindowFocus: true,
    refetchInterval: (query) => pollEvery(query.state.data),
  })
}

/** When an automatic download ends, what it brought is read again, on whichever screen is open. */
export function useRefreshWhenAutomaticDownloadEnds(): void {
  const queryClient = useQueryClient()
  const running = Boolean(useSchedule().data?.running)
  const wasRunning = useRef(false)
  useEffect(() => {
    if (wasRunning.current && !running) {
      for (const key of ['clients', 'invoices', 'proposed-rules', 'auth']) {
        void queryClient.invalidateQueries({ queryKey: [key] })
      }
    }
    wasRunning.current = running
  }, [running, queryClient])
}
