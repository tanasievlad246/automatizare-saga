import { CalendarClock, Check, LoaderCircle, TriangleAlert } from 'lucide-react'
import { Link } from 'react-router'
import { cn } from '@/lib/utils'
import type { ScheduleStatus } from '../types'
import { journalAddress, stateCard } from './scheduleTexts'
import { useNow } from './useNow'

const TONES = {
  attention: 'border-attention-border bg-attention text-attention-foreground',
  done: 'border-transparent bg-done text-done-foreground',
  fresh: 'border-transparent bg-fresh text-fresh-foreground',
  plain: 'border-border bg-card text-card-foreground',
}
const ICONS = { attention: TriangleAlert, done: Check, fresh: LoaderCircle, plain: CalendarClock }

/** What the automatic download is doing now, or what happened the last time, in words. */
export function ScheduleStateCard({ status }: { status: ScheduleStatus }) {
  // The words for today and tomorrow follow the clock, which the page keeps current.
  const card = stateCard(status, useNow())
  const Icon = ICONS[card.tone]
  return (
    <div role="status" className={cn('flex items-start gap-3.5 rounded-2xl border px-5.5 py-4.5', TONES[card.tone])}>
      <Icon aria-hidden className={cn('mt-1 size-6 shrink-0', card.tone === 'fresh' && 'animate-spin motion-reduce:animate-none')} />
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <p className="text-[1.125rem] font-bold">{card.title}</p>
        <p className="text-lg">{card.text}</p>
        {(card.journal || card.clients) && (
          <div className="mt-1 flex flex-wrap gap-x-6">
            {card.journal && <Link to={journalAddress(status.last_run?.trace)} className="min-h-11 content-center font-semibold">Vezi în jurnal</Link>}
            {card.clients && <Link to="/" className="min-h-11 content-center font-semibold">Vezi clienții</Link>}
          </div>
        )}
      </div>
    </div>
  )
}
