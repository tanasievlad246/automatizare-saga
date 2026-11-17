import { MutationObserver, QueryClient, QueryObserver } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import { describeEvidence } from './ruleEvidence'
import { conditionInWords, reloadWhatARuleChanges, ruleFromProposal, shownOutOf } from './proposedRule'

describe('a proposed rule', () => {
  const byWords = { cont: '302', keywords: ['ciment', 'var'], supplier_cuis: [], supplier_name: null }
  const bySupplier = { cont: '628', keywords: [], supplier_cuis: ['87654321'], supplier_name: 'Service Auto Nord SRL' }

  it('becomes a rule for every client, named after its words', () => {
    expect(ruleFromProposal(byWords)).toEqual({
      name: 'ciment, var', cont: '302', keywords: ['ciment', 'var'], supplier_cuis: [],
      item_codes: [], commodity_prefixes: [], client_cui: null, enabled: true, direction: 'received',
    })
  })

  it('is named after the supplier when it is for a supplier', () => {
    expect(ruleFromProposal(bySupplier).name).toBe('Service Auto Nord SRL')
    expect(ruleFromProposal(bySupplier).supplier_cuis).toEqual(['87654321'])
    expect(ruleFromProposal({ ...bySupplier, supplier_name: null }).name).toBe('furnizor 87654321')
  })

  it('has no name while it looks for nothing', () => {
    expect(ruleFromProposal({ ...bySupplier, supplier_cuis: [] }).name).toBe('')
  })

  it('reads as the second half of "Dacă …"', () => {
    expect(conditionInWords(byWords)).toBe('pe factură scrie: ciment, var')
    expect(conditionInWords(bySupplier)).toBe('factura este de la Service Auto Nord SRL')
    expect(conditionInWords({ ...bySupplier, supplier_name: null })).toBe('furnizorul are CUI 87654321')
  })
})

describe('the list of proposed rules', () => {
  it('says how many are shown when there are more', () => {
    expect(shownOutOf(20, 21)).toBe('Sunt afișate primele 20 din 21 de propuneri.')
    expect(shownOutOf(20, 105)).toBe('Sunt afișate primele 20 din 105 propuneri.')
  })

  it('keeps the button busy until the lists are read again, so a second press cannot repeat the rule', async () => {
    const queryClient = new QueryClient()
    let reads = 0
    let letSecondReadArrive = () => {}
    const list = new QueryObserver(queryClient, {
      queryKey: ['proposed-rules'],
      queryFn: () =>
        ++reads === 1 ? 'before' : new Promise<string>((resolve) => { letSecondReadArrive = () => resolve('after') }),
    })
    const stopWatching = list.subscribe(() => {})
    await vi.waitFor(() => expect(list.getCurrentResult().data).toBe('before'))

    const create = new MutationObserver(queryClient, {
      mutationFn: async () => 'created',
      onSuccess: () => reloadWhatARuleChanges(queryClient),
    })
    const created = create.mutate()
    await vi.waitFor(() => expect(reads).toBe(2))
    const whileTheProposalIsStillShown = create.getCurrentResult().isPending
    letSecondReadArrive()
    await created
    stopWatching()

    expect(whileTheProposalIsStillShown).toBe(true)
    expect(create.getCurrentResult().isPending).toBe(false)
    expect(list.getCurrentResult().data).toBe('after')
  })
})

describe('how a rule would have done', () => {
  const said = (byCont: Record<string, number>, cont = '302') =>
    describeEvidence({ matches: Object.values(byCont).reduce((sum, count) => sum + count, 0), by_cont: byCont }, cont, 90)

  it('agrees when every matched invoice is on the account of the rule', () => {
    expect(said({ '302': 1 })).toEqual({
      text: 'S-ar fi potrivit la o factură din ultimele 90 de zile, pe contul 302.', tone: 'agrees',
    })
    expect(said({ '302': 2 }).text).toBe('S-ar fi potrivit la 2 facturi din ultimele 90 de zile, amândouă pe contul 302.')
    expect(said({ '302': 3 }).text).toBe('S-ar fi potrivit la 3 facturi din ultimele 90 de zile, toate pe contul 302.')
    expect(said({ '302': 25 }).text).toBe('S-ar fi potrivit la 25 de facturi din ultimele 90 de zile, toate pe contul 302.')
  })

  it('differs when some are on other accounts, naming the account of the rule first', () => {
    expect(said({ '371': 1, '302': 4, '628': 2 })).toEqual({
      text: 'S-ar fi potrivit la 7 facturi din ultimele 90 de zile: 4 pe contul 302, 2 pe contul 628 și una pe contul 371.',
      tone: 'differs',
    })
  })

  it('differs when all of them are on another account', () => {
    expect(said({ '371': 2 })).toEqual({
      text: 'S-ar fi potrivit la 2 facturi din ultimele 90 de zile, amândouă pe contul 371.', tone: 'differs',
    })
  })

  it('says so when it matches nothing', () => {
    expect(said({})).toEqual({ text: 'Nu s-ar fi potrivit la nicio factură din ultimele 90 de zile.', tone: 'none' })
  })
})
