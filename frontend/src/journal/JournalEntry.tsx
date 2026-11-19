import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { formatClock } from '../format'
import type { JournalLine } from '../types'
import { detailText } from './details'
import { areaName, describeEvent, formatDuration, LEVEL_NAMES } from './eventTexts'

const LEVEL_LOOKS: Record<JournalLine['level'], string> = {
  detail: 'bg-background text-muted-foreground',
  info: 'bg-muted text-foreground',
  warning: 'bg-attention text-attention-foreground',
  error: 'bg-destructive/15 text-destructive',
}

/**
 * One line of the journal: when, how serious, where, and what happened in plain words.
 * Opened, it shows the program's own line, the details and the way to the whole operation.
 */
export function JournalEntry({ line, onShowOperation }: { line: JournalLine; onShowOperation?: (trace: string) => void }) {
  const [open, setOpen] = useState(false)
  const details = Object.entries(line.data).filter(([name]) => name !== 'traceback')
  const Arrow = open ? ChevronDown : ChevronRight

  return (
    <div className="border-t px-4.5 py-3">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex w-full cursor-pointer flex-wrap items-baseline gap-x-3.5 gap-y-1.5 text-left outline-none focus-visible:ring-3 focus-visible:ring-ring"
      >
        <Arrow aria-hidden className="size-4.5 shrink-0 self-center text-muted-foreground" />
        <span className="shrink-0 text-muted-foreground tabular-nums">{formatClock(line.at)}</span>
        {/* As wide as its longest word whatever it says, so the zones after it line up. */}
        <Badge className={cn('min-w-[6.5rem] shrink-0 justify-center', LEVEL_LOOKS[line.level])}>{LEVEL_NAMES[line.level]}</Badge>
        <span className="w-40 shrink-0 text-muted-foreground">{areaName(line.area)}</span>
        {/* A small basis keeps the sentence on the row in a narrow window; it wraps inside its own
            cell. A path without spaces breaks anywhere instead of spilling. */}
        <span className="min-w-0 flex-[1_1_200px] [overflow-wrap:anywhere]">{describeEvent(line)}</span>
      </button>
      {open && (
        <div className="mt-2.5 ml-8 flex flex-col gap-2 rounded-lg bg-background px-3.5 py-3 text-[0.94rem]">
          <p className="[overflow-wrap:anywhere]"><span className="font-semibold">Detalii tehnice:</span> {line.message}</p>
          {(details.length > 0 || line.duration_ms !== null) && (
            <p className="font-mono text-[0.88rem] break-words">
              {details.map(([name, value]) => `${name}: ${detailText(value)}`).join(' · ')}
              {line.duration_ms !== null && `${details.length ? ' · ' : ''}durată: ${formatDuration(line.duration_ms)}`}
            </p>
          )}
          {typeof line.data.traceback === 'string' && (
            <pre className="max-h-64 overflow-auto rounded-md bg-card p-3 font-mono text-[0.82rem] whitespace-pre-wrap">{line.data.traceback}</pre>
          )}
          {line.trace && onShowOperation && (
            <Button variant="link" className="h-auto min-h-9 self-start px-0" onClick={() => onShowOperation(line.trace!)}>
              Arată tot ce s-a întâmplat în această operațiune
            </Button>
          )}
        </div>
      )}
    </div>
  )
}
