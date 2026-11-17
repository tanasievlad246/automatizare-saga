import { describe, expect, it } from 'vitest'
import { placeOf, rememberPlace } from './listPlace'

describe('the place a list was left at', () => {
  it('is the list itself when it was never seen', () => {
    expect(placeOf('/clienti/111')).toBe('/clienti/111')
  })

  it('is the list as it was last seen, page and filters with it', () => {
    rememberPlace('/clienti/222', 'arata=toate&pagina=3')
    expect(placeOf('/clienti/222')).toBe('/clienti/222?arata=toate&pagina=3')
  })

  it('is kept for each list apart', () => {
    rememberPlace('/clienti/333', 'pagina=2')
    rememberPlace('/clienti/444', 'cauta=apa')
    expect(placeOf('/clienti/333')).toBe('/clienti/333?pagina=2')
  })

  it('is the bare list again once the list was seen without anything chosen', () => {
    rememberPlace('/', 'pagina=4')
    rememberPlace('/', '')
    expect(placeOf('/')).toBe('/')
  })
})
