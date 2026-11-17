import { describe, expect, it } from 'vitest'
import { jevOdds } from './jevOdds'

const ACCOUNTS = { '302': 'Materiale consumabile', '371': 'Mărfuri', '628': 'Alte servicii', '6022': 'Combustibil', '626': 'Telefonie' }

describe('how likely Jev found each account', () => {
  it('lists the accounts from the most likely, each with what it is for, and "none of these" by its name', () => {
    const odds = jevOdds({ '302': 0.91, '371': 0.06, '628': 0.02, altul: 0.01, '6022': 0.004, '626': 0 }, ACCOUNTS, '302')

    expect(odds.rows.map((row) => [row.label, row.description, row.share, row.chosen, row.none])).toEqual([
      ['302', 'Materiale consumabile', 0.91, true, false],
      ['371', 'Mărfuri', 0.06, false, false],
      ['628', 'Alte servicii', 0.02, false, false],
      ['Niciunul din listă', null, 0.01, false, true],
    ])
    expect(odds.below).toBe('Celelalte 2 conturi (626, 6022): sub 1%.')
  })

  it('counts an account Jev gave no figure for among the unlikely ones', () => {
    expect(jevOdds({ '302': 0.9, altul: 0.1 }, ACCOUNTS, '302').below).toBe('Celelalte 4 conturi (371, 626, 628, 6022): sub 1%.')
    expect(jevOdds({ '302': 0.9, '371': 0.1 }, { '302': 'a', '371': 'b', '628': 'c' }, '302').below).toBe('Celălalt cont (628): sub 1%.')
  })

  it('says "de" before twenty or more accounts, as Romanian does', () => {
    const many = Object.fromEntries(Array.from({ length: 23 }, (_, index) => [String(600 + index), 'x']))

    expect(jevOdds({ '600': 0.9 }, many, '600').below?.startsWith('Celelalte 22 de conturi (601, 602')).toBe(true)
  })

  it('marks "none of these" as the choice when Jev made it', () => {
    const odds = jevOdds({ altul: 0.72, '628': 0.18 }, ACCOUNTS, null)

    expect(odds.rows[0]).toMatchObject({ label: 'Niciunul din listă', chosen: true, none: true })
  })

  it('keeps an account Jev named that is no longer on the list, without a description', () => {
    expect(jevOdds({ '999': 0.8 }, {}, '999').rows).toEqual([
      { key: '999', label: '999', description: null, share: 0.8, chosen: true, none: false },
    ])
  })

  it('has nothing to show when Jev gave no figures', () => {
    expect(jevOdds({}, ACCOUNTS, null)).toEqual({ rows: [], below: null })
  })
})
