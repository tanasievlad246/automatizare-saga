import { DateField } from '@/components/DateField'
import { PillTabs } from '@/components/PillTabs'
import { countOf, today } from '../format'
import type { SchedulePeriod } from '../types'
import { PERIOD_DAYS, periodSays } from './scheduleTexts'

const LAST_DAYS = PERIOD_DAYS.map((days) => ({ value: days, label: `Ultimele ${countOf(days, 'zi', 'zile')}` }))

/** Which invoices each automatic download brings: those of the last days, or those between two chosen days. */
export function SchedulePeriodFields({ period, onChange }: { period: SchedulePeriod; onChange: (period: SchedulePeriod) => void }) {
  // While a number of days is chosen the two date fields are empty; a date typed into one starts a period of dates.
  const dates = 'days' in period ? { start: '', end: '' } : period
  const lastStart = dates.end && dates.end < today() ? dates.end : today()
  return (
    <div className="flex flex-col gap-2.5">
      <h3 className="font-sans text-lg font-bold">Facturile din ce perioadă?</h3>
      <PillTabs label="Perioada" options={LAST_DAYS} value={'days' in period ? period.days : null} onChange={(days) => onChange({ days })} />
      <div className="flex flex-col gap-3 rounded-xl bg-background px-5 py-4.5">
        <p className="font-bold">sau alegeți zilele</p>
        <div className="flex flex-wrap gap-x-5 gap-y-3.5">
          <DateField id="schedule-start" label="De la" value={dates.start} max={lastStart} onChange={(start) => onChange({ ...dates, start })} />
          <DateField id="schedule-end" label="Până la" value={dates.end} min={dates.start || undefined} onChange={(end) => onChange({ ...dates, end })} />
        </div>
      </div>
      <p>{periodSays(period)}</p>
      <p className="text-muted-foreground">
        ANAF păstrează facturile doar 60 de zile. Facturile descărcate deja nu se descarcă a doua oară.
      </p>
    </div>
  )
}
