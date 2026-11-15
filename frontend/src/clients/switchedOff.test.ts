import { describe, expect, it } from 'vitest'
import type { Client } from '../types'
import { switchedOffLine, switchedOn } from './switchedOff'

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
