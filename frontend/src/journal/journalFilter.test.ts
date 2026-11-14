import { describe, expect, it } from 'vitest'
import { today } from '../format'
import type { JournalChoice } from './JournalFilters'
import { filterFor } from './journalFilter'

const choice = (changed: Partial<JournalChoice> = {}): JournalChoice => ({
  shown: 'tot', details: false, area: '', period: 'azi', text: '', ...changed,
})

describe('what the journal asks the program for', () => {
  it('leaves out whatever was not chosen', () => {
    expect(filterFor(choice())).toEqual({
      problems: undefined, details: undefined, area: undefined, q: undefined, since: `${today()}T00:00:00`,
    })
  })

  it('asks for what was chosen', () => {
    expect(filterFor(choice({ shown: 'probleme', details: true, area: 'sync', text: ' Alfa ' }))).toMatchObject({
      problems: true, details: true, area: 'sync', q: 'Alfa',
    })
  })

  it('asks for the details with the zone "Pagina", which holds nothing else', () => {
    expect(filterFor(choice({ area: 'page' })).details).toBe(true)
  })
})
