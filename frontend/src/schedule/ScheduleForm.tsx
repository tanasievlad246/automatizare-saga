import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, X } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { PillTabs } from '@/components/PillTabs'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { api } from '../api'
import { showError } from '../errorMessages'
import type { ScheduleStatus } from '../types'
import { DAY_NAMES, formProblem, MOST_TIMES } from './scheduleTexts'

// The hours offered, in this order, when a person adds one.
const SUGGESTED_TIMES = ['12:00', '16:00', '10:00', '18:00']

const sorted = <T,>(items: T[]) => [...items].sort()

/** What to download when: nothing changes until "Salvează" is pressed. */
export function ScheduleForm({ saved }: { saved: ScheduleStatus }) {
  const queryClient = useQueryClient()
  const [enabled, setEnabled] = useState(saved.enabled)
  const [days, setDays] = useState(saved.days)
  const [times, setTimes] = useState(saved.times)
  const save = useMutation({
    mutationFn: () => api.saveSchedule({ enabled, days: sorted(days), times: sorted(times) }),
    onSuccess: (status) => {
      queryClient.setQueryData(['schedule'], status)
      toast.success('Descărcarea automată a fost salvată.')
    },
    onError: showError,
  })

  const problem = formProblem(enabled, days, times)
  const unchanged =
    enabled === saved.enabled &&
    sorted(days).join() === sorted(saved.days).join() &&
    sorted(times).join() === sorted(saved.times).join()

  const toggleDay = (index: number) => setDays(days.includes(index) ? days.filter((day) => day !== index) : [...days, index])
  const setTime = (at: number, time: string) => setTimes(times.map((each, index) => (index === at ? time : each)))
  const addTime = () => {
    const next = SUGGESTED_TIMES.find((time) => !times.includes(time))
    if (next) setTimes([...times, next])
  }

  return (
    <section aria-label="Când să descarce" className="flex flex-col gap-5 rounded-2xl border bg-card px-5.5 py-5">
      <h2 className="font-sans text-xl font-bold">Când să descarce</h2>
      <PillTabs
        label="Descărcare automată"
        value={enabled ? 'on' : 'off'}
        onChange={(value) => setEnabled(value === 'on')}
        options={[{ value: 'off', label: 'Oprită' }, { value: 'on', label: 'Pornită' }]}
      />

      <div className="flex flex-col gap-2.5">
        <h3 className="font-sans text-lg font-bold">În ce zile?</h3>
        <div role="group" aria-label="Zilele" className="flex flex-wrap gap-2">
          {DAY_NAMES.map((name, index) => {
            const chosen = days.includes(index)
            return (
              <button
                key={name}
                type="button"
                aria-pressed={chosen}
                onClick={() => toggleDay(index)}
                className={cn(
                  'inline-flex min-h-12 items-center gap-1.5 rounded-xl border-2 px-4 font-semibold outline-none focus-visible:ring-3 focus-visible:ring-ring/50',
                  chosen ? 'border-fresh-foreground bg-fresh text-fresh-foreground' : 'border-input bg-card hover:bg-muted',
                )}
              >
                {chosen && <Check aria-hidden className="size-4.5" />}
                {name}
              </button>
            )
          })}
        </div>
      </div>

      <div className="flex flex-col gap-2.5">
        <h3 className="font-sans text-lg font-bold">La ce oră?</h3>
        <div className="flex flex-col items-start gap-2.5">
          {times.map((time, index) => (
            <div key={index} className="flex items-center gap-2">
              <Input
                type="time"
                aria-label={`Ora ${index + 1}`}
                className="w-40"
                value={time}
                onChange={(event) => setTime(index, event.target.value)}
              />
              {times.length > 1 && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={`Scoate ora ${time}`}
                  onClick={() => setTimes(times.filter((_, at) => at !== index))}
                >
                  <X aria-hidden className="text-muted-foreground" />
                </Button>
              )}
            </div>
          ))}
          {times.length < MOST_TIMES && (
            <Button type="button" variant="link" className="px-0" onClick={addTime}>Adaugă încă o oră</Button>
          )}
        </div>
        <p className="text-muted-foreground">Cel mult patru ore pe zi.</p>
      </div>

      <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
        <Button size="lg" disabled={problem !== null || unchanged || save.isPending} onClick={() => save.mutate()}>
          Salvează
        </Button>
        {problem ? (
          <p role="alert" className="font-semibold text-attention-foreground">{problem}</p>
        ) : (
          <p className="text-muted-foreground">Ce schimbați aici se aplică după ce apăsați „Salvează”.</p>
        )}
      </div>
    </section>
  )
}
