import { describe, expect, it } from 'vitest'
import { pageFrom, pageNumbers, pageOf, rangeLine } from './paging'

const numbers = (count: number) => Array.from({ length: count }, (_, index) => index + 1)

describe('one page of a list', () => {
  it('holds the rows of that page and says which they are', () => {
    const page = pageOf(numbers(312), 2, 25)
    expect(page.items).toEqual(numbers(50).slice(25))
    expect(page).toMatchObject({ page: 2, pages: 13, first: 26, last: 50, total: 312 })
  })

  it('ends with the rows that are left', () => {
    const page = pageOf(numbers(312), 13, 25)
    expect(page.items).toEqual([301, 302, 303, 304, 305, 306, 307, 308, 309, 310, 311, 312])
    expect(page).toMatchObject({ first: 301, last: 312, pages: 13 })
  })

  it('shows the last page when the one asked for is past the end, as after the last row of a page left the list', () => {
    expect(pageOf(numbers(50), 3, 25)).toMatchObject({ page: 2, first: 26, last: 50 })
    expect(pageOf(numbers(25), 2, 25)).toMatchObject({ page: 1, pages: 1, first: 1, last: 25 })
  })

  it('is one empty page when there is nothing', () => {
    expect(pageOf([], 4, 25)).toEqual({ items: [], page: 1, pages: 1, first: 0, last: 0, total: 0 })
  })

  it('never starts before the first page', () => {
    expect(pageOf(numbers(30), 0, 25).page).toBe(1)
    expect(pageOf(numbers(30), -2, 25).page).toBe(1)
  })
})

describe('the page numbers under a list', () => {
  it('are all there when there are few', () => {
    expect(pageNumbers(1, 1)).toEqual([1])
    expect(pageNumbers(4, 7)).toEqual([1, 2, 3, 4, 5, 6, 7])
  })

  it('show the first ones, a gap and the last at the start', () => {
    expect(pageNumbers(1, 13)).toEqual([1, 2, 3, null, 13])
    expect(pageNumbers(2, 13)).toEqual([1, 2, 3, null, 13])
  })

  it('show the first, the pages around the one shown and the last in the middle', () => {
    expect(pageNumbers(7, 13)).toEqual([1, null, 6, 7, 8, null, 13])
  })

  it('show the first, a gap and the last ones at the end', () => {
    expect(pageNumbers(13, 13)).toEqual([1, null, 11, 12, 13])
    expect(pageNumbers(12, 13)).toEqual([1, null, 11, 12, 13])
  })

  it('write the page itself instead of a gap that would hide only one page', () => {
    expect(pageNumbers(4, 13)).toEqual([1, 2, 3, 4, 5, null, 13])
    expect(pageNumbers(10, 13)).toEqual([1, null, 9, 10, 11, 12, 13])
  })
})

describe('the page asked for in the address', () => {
  it('is read as a whole number from 1 up', () => {
    expect(pageFrom('3')).toBe(3)
    expect(pageFrom(null)).toBe(1)
    expect(pageFrom('')).toBe(1)
    expect(pageFrom('0')).toBe(1)
    expect(pageFrom('-2')).toBe(1)
    expect(pageFrom('2.5')).toBe(1)
    expect(pageFrom('abc')).toBe(1)
  })
})

describe('the line beside the page numbers', () => {
  const invoices = { one: 'Factura', many: 'Facturile' }

  it('says which rows are seen and of how many', () => {
    expect(rangeLine(pageOf(numbers(312), 1, 25), invoices)).toBe('Facturile 1–25 din 312')
    expect(rangeLine(pageOf(numbers(312), 13, 25), invoices)).toBe('Facturile 301–312 din 312')
  })

  it('names a single row on the last page alone', () => {
    expect(rangeLine(pageOf(numbers(26), 2, 25), invoices)).toBe('Factura 26 din 26')
  })

  it('can say the rows are the ones found', () => {
    expect(rangeLine(pageOf(numbers(31), 1, 20), { one: 'Clientul', many: 'Clienții' }, 'găsiți')).toBe('Clienții 1–20 din 31 găsiți')
  })
})
