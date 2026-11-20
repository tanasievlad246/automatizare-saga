import { describe, expect, it } from 'vitest'
import { byName, onFirst, searchClients, shownLine, whoIsOn } from './clientSearch'

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

describe('the order of the client list', () => {
  it('goes by name as Romanian is ordered, so a name with Ș, Ț, Ă or Î is not put after Z', () => {
    const listed = [{ name: 'Zeta SRL', cui: '1' }, { name: 'Țesătoria SRL', cui: '2' }, { name: 'Ăla Bun SRL', cui: '3' }, { name: 'beta SRL', cui: '4' }]
    expect(byName(listed).map((client) => client.name)).toEqual(['Ăla Bun SRL', 'beta SRL', 'Țesătoria SRL', 'Zeta SRL'])
    expect(listed[0].name).toBe('Zeta SRL') // the list given is left as it was
  })
})

describe('the clients that are on come first', () => {
  const on = (name: string, cui: string) => ({ name, cui, enabled: true })
  const off = (name: string, cui: string) => ({ name, cui, enabled: false })
  const names = (clients: { name: string }[]) => clients.map((client) => client.name)

  it('puts the clients that are on before those that are off, each group in the order given', () => {
    const listed = [off('Agro', '1'), on('Alfa', '2'), off('Cabinet', '3'), on('Zefir', '4')]
    expect(names(onFirst(listed, whoIsOn(listed)))).toEqual(['Alfa', 'Zefir', 'Agro', 'Cabinet'])
    expect(names(listed)).toEqual(['Agro', 'Alfa', 'Cabinet', 'Zefir']) // the list given is left as it was
  })

  it('leaves a client switched since the list was opened where it was', () => {
    const atOpen = whoIsOn([on('Alfa', '2'), on('Beta', '5'), off('Cabinet', '3')])
    const now = [off('Alfa', '2'), on('Beta', '5'), on('Cabinet', '3')] // Alfa switched off, Cabinet on
    expect(names(onFirst(now, atOpen))).toEqual(['Alfa', 'Beta', 'Cabinet'])
  })

  it('places a client added since by how it stands now', () => {
    const atOpen = whoIsOn([on('Alfa', '2'), off('Cabinet', '3')])
    const now = [on('Alfa', '2'), off('Cabinet', '3'), on('Delta', '6'), off('Epsilon', '7')]
    expect(names(onFirst(now, atOpen))).toEqual(['Alfa', 'Delta', 'Cabinet', 'Epsilon'])
  })

  it('goes by how each stands now until the list has been opened', () => {
    expect(names(onFirst([off('Agro', '1'), on('Alfa', '2')], null))).toEqual(['Alfa', 'Agro'])
  })

  it('keeps the order in what a search finds', () => {
    const listed = [off('Agro SRL', '1'), on('Alfa SRL', '2'), on('Zefir SRL', '4')]
    expect(names(searchClients(onFirst(listed, whoIsOn(listed)), 'srl'))).toEqual(['Alfa SRL', 'Zefir SRL', 'Agro SRL'])
  })
})
