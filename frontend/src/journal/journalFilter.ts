import type { JournalFilter } from '../api'
import { daysAgo, today } from '../format'
import type { JournalChoice } from './JournalFilters'

/** What the program is asked for, from what was chosen above the list. */
export function filterFor(choice: JournalChoice): JournalFilter {
  return {
    problems: choice.shown === 'probleme' || undefined,
    // The zone "Pagina" holds nothing but details: without them it would always be empty.
    details: choice.details || choice.area === 'page' || undefined,
    area: choice.area || undefined,
    q: choice.text.trim() || undefined,
    since: `${choice.period === 'azi' ? today() : daysAgo(Number(choice.period))}T00:00:00`,
  }
}
