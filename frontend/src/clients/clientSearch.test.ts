import { describe, expect, it } from 'vitest'
import { searchClients, shownLine } from './clientSearch'

const ALFA = { name: 'Alfa Construct SRL', cui: '12345674' }
const BRUTARIA = { name: 'Brutăria Soarelui SRL', cui: '14399840' }
const CABINET = { name: 'Cabinet Medical Ionescu', cui: '18547290' }
const GAMA = { name: 'Gama Trans S.R.L.', cui: '27845391' }
const TIRIAC = { name: 'Ţiriac & Şerban', cui: '10000008' } // written with the old cedilla letters
const CLIENTS = [ALFA, BRUTARIA, CABINET, GAMA, TIRIAC]

const found = (typed: string) => searchClients(CLIENTS, typed).map((client) => client.name)

describe('searching the client list', () => {
  it('shows everyone, in their order, while nothing is typed', () => {
    expect(searchClients(CLIENTS, '')).toEqual(CLIENTS)
    expect(searchClients(CLIENTS, '   ')).toEqual(CLIENTS)
  })

  it('finds by a part of the name, whatever the case', () => {
    expect(found('alfa')).toEqual([ALFA.name])
    expect(found('MEDICAL')).toEqual([CABINET.name])
    expect(found('  onst ')).toEqual([ALFA.name])
    expect(found('srl')).toEqual([ALFA.name, BRUTARIA.name, GAMA.name])
  })

  it('does not mind diacritics, typed or not, new or old', () => {
    expect(found('brutaria')).toEqual([BRUTARIA.name])
    expect(found('Brutăria')).toEqual([BRUTARIA.name])
    expect(found('brutâria')).toEqual([BRUTARIA.name])
    expect(found('tiriac serban')).toEqual([TIRIAC.name])
    expect(found('țiriac')).toEqual([TIRIAC.name])
  })

  it('does not mind dots and other signs', () => {
    expect(found('s.r.l.')).toEqual([ALFA.name, BRUTARIA.name, GAMA.name])
    expect(found('gama trans srl')).toEqual([GAMA.name])
    expect(found('tiriac & serban')).toEqual([TIRIAC.name])
  })

  it('wants every word typed to be found', () => {
    expect(found('soarelui brut')).toEqual([BRUTARIA.name])
    expect(found('alfa medical')).toEqual([])
    expect(found('xyz')).toEqual([])
  })

  it('finds by the CUI, whole or a part of it, with or without RO', () => {
    expect(found('12345674')).toEqual([ALFA.name])
    expect(found('1439')).toEqual([BRUTARIA.name])
    expect(found('290')).toEqual([CABINET.name])
    expect(found('RO12345674')).toEqual([ALFA.name])
    expect(found('ro 12345674')).toEqual([ALFA.name])
    expect(found('RO55')).toEqual([])
  })

  it('finds by a name and a CUI together', () => {
    expect(found('alfa 1234')).toEqual([ALFA.name])
    expect(found('alfa 1439')).toEqual([])
  })

  it('finds a CUI kept with its RO', () => {
    expect(searchClients([{ name: 'Delta', cui: 'RO4221306' }], '4221')).toHaveLength(1)
    expect(searchClients([{ name: 'Delta', cui: 'RO4221306' }], 'ro4221306')).toHaveLength(1)
  })
})

describe('the line under the search field', () => {
  it('says how many of the clients are seen', () => {
    expect(shownLine(1, 14)).toBe('Se vede un client din 14.')
    expect(shownLine(2, 14)).toBe('Se văd 2 clienți din 14.')
    expect(shownLine(25, 140)).toBe('Se văd 25 de clienți din 140.')
  })

  it('says nothing while every client is seen', () => {
    expect(shownLine(14, 14)).toBeNull()
  })
})
