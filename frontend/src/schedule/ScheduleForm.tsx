import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, X } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Notice } from '@/components/Notice'
import { PillTabs } from '@/components/PillTabs'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { api } from '../api'
import { showError } from '../errorMessages'
import type { ScheduleStatus } from '../types'
import { DAY_NAMES, formProblem, MOST_TIMES, onSavedChange, ownSaveArrival, sameSchedule, type ScheduleChoice } from './scheduleTexts'

// The hours offered, in this order, when a person adds one.
const SUGGESTED_TIMES = ['12:00', '16:00', '10:00', '18:00']

const sorted = <T,>(items: T[]) => [...items].sort()
const choiceOf = ({ enabled, days, times }: ScheduleChoice): ScheduleChoice => ({ enabled, days, times })

/**
 * What to download when: nothing changes until "Salvează" is pressed. The form stays mounted
 * (so focus stays where it is) and follows the saved schedule only while it holds no edits.
 */
export function ScheduleForm({ saved }: { saved: ScheduleStatus }) {
  const queryClient = useQueryClient()
  // `followed` is the saved schedule the draft started from; the draft is what is being edited.
  const [followed, setFollowed] = useState<ScheduleChoice>(choiceOf(saved))
  const [draft, setDraft] = useState<ScheduleChoice>(choiceOf(saved))
  // Her own save: its answer, and the schedule the form followed before it, until the page shows the answer.
  const [answered, setAnswered] = useState<{ answer: ScheduleChoice; before: ScheduleChoice } | null>(null)
  const { enabled, days, times } = draft

  const arrival = answered && ownSaveArrival(saved, answered.answer, answered.before)
  let notice = false
  if (arrival === 'arrived') {
    // Follow the answer and keep what she typed since.
    setFollowed(choiceOf(saved))
    setAnswered(null)
  } else if (arrival !== 'waiting') {
    // No save is waiting, or something else was saved meanwhile (then `followed` is still the old one).
    if (arrival === 'overtaken') setAnswered(null)
    const change = onSavedChange(draft, followed, saved)
    if (change === 'follow') {
      setFollowed(choiceOf(saved))
      setDraft(choiceOf(saved))
    }
    notice = change === 'notice'
  }
  const showSaved = () => {
    setFollowed(choiceOf(saved))
    setDraft(choiceOf(saved))
    setAnswered(null)
  }

  const save = useMutation({
    mutationFn: (choice: ScheduleChoice) => api.saveSchedule({ ...choice, days: sorted(choice.days), times: sorted(choice.times) }),
    onSuccess: (status) => {
      setAnswered({ answer: choiceOf(status), before: followed })
      // A read that started before her save must not put the old schedule back.
      void queryClient.cancelQueries({ queryKey: ['schedule'] })
      queryClient.setQueryData(['schedule'], status)
      toast.success('Descărcarea automată a fost salvată.')
    },
    onError: showError,
  })

  const problem = formProblem(enabled, days, times)
  const unchanged = sameSchedule(draft, followed)
  const setEnabled = (value: boolean) => setDraft({ ...draft, enabled: value })
  const setDays = (value: number[]) => setDraft({ ...draft, days: value })
  const setTimes = (value: string[]) => setDraft({ ...draft, times: value })

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

      {notice && (
        <Notice tone="attention" className="flex-wrap items-center">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
            <p className="min-w-0 flex-[1_1_320px] font-semibold">
              Descărcarea automată a fost schimbată din altă parte cât timp lucrați aici.
            </p>
            <Button type="button" className="bg-attention-foreground hover:bg-attention-foreground/85" onClick={showSaved}>
              Arată ce este salvat
            </Button>
          </div>
        </Notice>
      )}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
        <Button size="lg" disabled={problem !== null || unchanged || save.isPending} onClick={() => save.mutate(draft)}>
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
