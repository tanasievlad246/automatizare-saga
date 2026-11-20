import { describe, expect, it } from 'vitest'
import type { Client } from '../types'
import { allSwitch, headerLine, switchAllQuestion, switchedAllToast, switchedOffLine, switchedOn } from './switchedOff'

const client = (name: string, enabled: boolean) => ({ name, enabled }) as Client

describe('switchedOn', () => {
  it('keeps the clients that are on, in their order', () => {
    const list = [client('Alfa', true), client('Beta', false), client('Gama', true)]
    expect(switchedOn(list).map((c) => c.name)).toEqual(['Alfa', 'Gama'])
  })
})

describe('switchedOffLine', () => {
  it('says nothing while every client is on', () => {
    expect(switchedOffLine(4, 0)).toBeNull()
    expect(switchedOffLine(0, 0)).toBeNull()
  })
  it('counts the clients that are downloaded and those that are off', () => {
    expect(switchedOffLine(3, 1)).toBe('Se descarcă 3 din cei 4 clienți. Un client este oprit.')
    expect(switchedOffLine(1, 2)).toBe('Se descarcă 1 din cei 3 clienți. 2 clienți sunt opriți.')
    expect(switchedOffLine(5, 20)).toBe('Se descarcă 5 din cei 25 de clienți. 20 de clienți sunt opriți.')
  })
  it('says so when every client is off', () => {
    expect(switchedOffLine(0, 2)).toBe('Toți clienții sunt opriți. Porniți cel puțin unul ca să descărcați facturi.')
  })
})

describe('the check in the header of the client list', () => {
  it('is ticked when every client is on, empty when none is, and in between otherwise', () => {
    expect(allSwitch(4, 0)).toBe('all')
    expect(allSwitch(0, 3)).toBe('none')
    expect(allSwitch(3, 1)).toBe('some')
  })

  it('says how many are on and how many are off', () => {
    expect(headerLine(3, 2)).toBe('3 porniți · 2 opriți')
    expect(headerLine(1, 1)).toBe('1 pornit · 1 oprit')
    expect(headerLine(24, 1)).toBe('24 porniți · 1 oprit')
  })

  it('says so when every client is on', () => {
    expect(headerLine(5, 0)).toBe('Toți cei 5 sunt porniți')
    expect(headerLine(1, 0)).toBe('Singurul client este pornit')
  })

  it('says why nothing can be downloaded when every client is off', () => {
    expect(headerLine(0, 5)).toBe('Toți cei 5 sunt opriți. Porniți cel puțin unul ca să descărcați facturi.')
    expect(headerLine(0, 1)).toBe('Singurul client este oprit. Porniți-l ca să descărcați facturi.')
  })
})

describe('the question before every client is switched', () => {
  it('asks before switching everyone off, and says what stops and what stays', () => {
    expect(switchAllQuestion(false, 5, 0, false)).toEqual({
      title: 'Opriți toți clienții?',
      lines: [
        'Se opresc toți cei 5 clienți.',
        'După oprire, programul nu mai descarcă facturi de la ANAF pentru niciun client, nici la descărcarea automată, până îi porniți din nou.',
      ],
      note: 'Facturile descărcate până acum rămân, cu conturile lor și cu fișierele pentru SAGA.',
      confirm: 'Da, oprește-i pe toți',
    })
    expect(switchAllQuestion(false, 25, 0, false).lines[0]).toBe('Se opresc toți cei 25 de clienți.')
    expect(switchAllQuestion(false, 1, 0, false).lines[0]).toBe('Se oprește singurul client.')
  })

  it('asks before switching everyone on, and counts the ones that are off', () => {
    expect(switchAllQuestion(true, 3, 2, false)).toEqual({
      title: 'Porniți toți clienții?',
      lines: [
        'Se pornesc cei 2 clienți opriți.',
        'De acum, facturile lor se descarcă împreună cu ale celorlalți, și la descărcarea automată.',
      ],
      note: null,
      confirm: 'Da, pornește-i pe toți',
    })
    // One client is switched on: "its" invoices, not "their".
    expect(switchAllQuestion(true, 3, 1, false).lines).toEqual([
      'Se pornește clientul oprit.',
      'De acum, facturile lui se descarcă împreună cu ale celorlalți, și la descărcarea automată.',
    ])
    expect(switchAllQuestion(true, 3, 22, false).lines[0]).toBe('Se pornesc cei 22 de clienți opriți.')
  })

  it('does not speak of the others when every client was off', () => {
    expect(switchAllQuestion(true, 0, 5, false).lines).toEqual([
      'Se pornesc toți cei 5 clienți.',
      'De acum, facturile lor se descarcă, și la descărcarea automată.',
    ])
    expect(switchAllQuestion(true, 0, 1, false).lines).toEqual([
      'Se pornește singurul client.',
      'De acum, facturile lui se descarcă, și la descărcarea automată.',
    ])
  })

  it('says that the clients a search hides are switched too', () => {
    const hidden = 'Se schimbă toți clienții, și cei care nu se văd acum în listă.'
    expect(switchAllQuestion(true, 3, 2, true).lines.at(-1)).toBe(hidden)
    expect(switchAllQuestion(false, 5, 0, true).lines.at(-1)).toBe(hidden)
  })
})

describe('after every client was switched', () => {
  it('says how they all stand now', () => {
    expect(switchedAllToast(false, 5)).toBe('Toți cei 5 clienți sunt opriți.')
    expect(switchedAllToast(true, 25)).toBe('Toți cei 25 de clienți sunt porniți.')
    expect(switchedAllToast(true, 1)).toBe('Clientul este pornit.')
    expect(switchedAllToast(false, 1)).toBe('Clientul este oprit.')
  })
})
