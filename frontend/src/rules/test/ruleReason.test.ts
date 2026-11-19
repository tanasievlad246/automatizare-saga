import { describe, expect, it } from 'vitest'
import type { TrialRule } from '../../types'
import { matchWords, ruleReason } from './ruleReason'

const rule = (more: Partial<TrialRule>): TrialRule => ({
  name: 'combustibil', line: 1, condition: 'keyword', found: 'motorina', prefix: null, client_only: false, also: [], ...more,
})

describe('why a rule gave a line its account', () => {
  it('names the word of the rule that is on the line', () => {
    expect(ruleReason(rule({}))).toEqual(['Regula „combustibil”: pe linie scrie „motorina”, unul din cuvintele regulii.'])
  })

  it('says a word ending in a star is the start of a word on the line', () => {
    expect(ruleReason(rule({ name: 'telecom', found: 'abonament telefon*' }))[0]).toBe(
      'Regula „telecom”: pe linie scrie un cuvânt care începe cu „abonament telefon”.',
    )
  })

  it('says the words a star found, and what the star stands for', () => {
    expect(ruleReason(rule({ name: 'telecom', found: 'abonament telefon*', matched: 'abonament telefonie' }))[0]).toBe(
      'Regula „telecom”: pe linie scrie „abonament telefonie”, care începe cu „abonament telefon”.',
    )
    expect(ruleReason(rule({ name: 'consumabile', found: '*cartus', matched: 'tonercartus' }))[0]).toBe(
      'Regula „consumabile”: pe linie scrie „tonercartus”, care se termină cu „cartus”.',
    )
    expect(ruleReason(rule({ name: 'consumabile', found: '*cartus*', matched: 'cartuse' }))[0]).toBe(
      'Regula „consumabile”: pe linie scrie „cartuse”, iar regula caută cuvinte care conțin „cartus”.',
    )
  })

  it('says a star at the start without the words found as the rule has it', () => {
    expect(ruleReason(rule({ name: 'consumabile', found: '*cartus*' }))[0]).toBe(
      'Regula „consumabile”: pe linie scrie un cuvânt care conține „cartus”.',
    )
    expect(ruleReason(rule({ name: 'consumabile', found: '*cartus' }))[0]).toBe(
      'Regula „consumabile”: pe linie scrie un cuvânt care se termină cu „cartus”.',
    )
  })

  it('says when the word is in the line\'s description', () => {
    expect(ruleReason(rule({ name: 'consumabile', found: 'compatibil', matched: 'compatibil', in_details: true }))[0]).toBe(
      'Regula „consumabile”: în descrierea liniei scrie „compatibil”, unul din cuvintele regulii.',
    )
  })

  it('says, for an invoice with one account, that the word is on its largest line', () => {
    expect(matchWords({ condition: 'keyword', found: 'motorina', prefix: null, matched: 'motorina', in_details: false }, 'largest')).toBe(
      ': pe linia cea mai mare scrie „motorina”, unul din cuvintele regulii',
    )
    expect(matchWords({ condition: 'keyword', found: '*cartus*', prefix: null, matched: 'cartus', in_details: true }, 'largest')).toBe(
      ': în descrierea liniei celei mai mari scrie „cartus”, iar regula caută cuvinte care conțin „cartus”',
    )
  })

  it('names the supplier, the article code, the barcode or the classification code', () => {
    expect(ruleReason(rule({ name: 'Dedeman', condition: 'supplier_cui', found: '2816464' }))[0]).toBe(
      'Regula „Dedeman”: factura vine de la CUI-ul 2816464, iar regula ia toate liniile acestui furnizor.',
    )
    expect(ruleReason(rule({ name: 'ciment', condition: 'seller_code', found: '10023' }))[0]).toBe(
      'Regula „ciment”: codul articolului, 10023, este unul din codurile regulii.',
    )
    expect(ruleReason(rule({ name: 'ciment', condition: 'barcode', found: '5941234567890' }))[0]).toBe(
      'Regula „ciment”: codul de bare, 5941234567890, este unul din codurile regulii.',
    )
    expect(ruleReason(rule({ name: 'carburanți', condition: 'commodity_code', found: '27101943', prefix: '2710' }))[0]).toBe(
      'Regula „carburanți”: codul de clasificare 27101943 începe cu 2710.',
    )
  })

  it('says only the name when the program did not say which condition', () => {
    expect(ruleReason(rule({ condition: null, found: null }))).toEqual(['Regula „combustibil”.'])
  })

  it('says the rules further down that would have matched too, and a rule for one client', () => {
    expect(ruleReason(rule({ also: ['transport'] }))[1]).toBe(
      'S-ar fi potrivit și regula „transport”, dar „combustibil” este mai sus în listă.',
    )
    expect(ruleReason(rule({ also: ['transport', 'diverse', 'auto'] }))[1]).toBe(
      'S-ar fi potrivit și regulile „transport”, „diverse” și „auto”, dar „combustibil” este mai sus în listă.',
    )
    expect(ruleReason(rule({ client_only: true }), 'Alfa Construct SRL')[1]).toBe('Este o regulă doar pentru Alfa Construct SRL.')
    expect(ruleReason(rule({ client_only: true }))[1]).toBe('Este o regulă doar pentru clientul ales.')
  })
})
