import { describe, expect, it } from 'vitest'
import type { SagaFilePer } from '../types'
import {
  NOTHING_SEEN, WHOLE, attempted, confirmed, downloaded, firstSight, hasChanged, looked, refused, seenAgain, seenKey, seenVersion,
} from './seenFiles'

/** What waits for a client: its files by name and version, and the version of them all together. */
const waiting = (filePer: SagaFilePer, version: string | null, files: Record<string, string>) => ({
  file_per: filePer,
  version,
  files: Object.entries(files).map(([name, fileVersion]) => ({ name, version: fileVersion })),
})

describe('one file for the client', () => {
  const first = waiting('client', 'v1', { 'F_A1.xml': 'v1' })

  it('is the same thing as all the client\'s files together', () => {
    expect(seenKey('F_A1.xml', first)).toBe(WHOLE)
    const seen = firstSight(NOTHING_SEEN, first)
    expect(seenVersion(seen, WHOLE)).toBe('v1')
  })

  it('keeps the version first seen, whatever the page reloads by itself', () => {
    const seen = firstSight(firstSight(NOTHING_SEEN, first), waiting('client', 'v2', { 'F_A1.xml': 'v2' }))
    expect(seenVersion(seen, WHOLE)).toBe('v1')
  })

  it('is the same file under another name: renamed, what was seen is still the older one', () => {
    const renamed = waiting('client', 'v2', { 'F_B7.xml': 'v2' }) // its first invoice changed
    const seen = firstSight(firstSight(NOTHING_SEEN, first), renamed)
    expect(seenVersion(seen, seenKey('F_B7.xml', renamed))).toBe('v1')
  })

  it('is seen as downloaded, even when the list on the page is older or newer', () => {
    const seen = downloaded(firstSight(NOTHING_SEEN, first), first, 'F_A1.xml', 'v3')
    expect(seenVersion(seen, WHOLE)).toBe('v3')
  })

  it('is seen as listed when the download did not say its version', () => {
    const now = waiting('client', 'v2', { 'F_A1.xml': 'v2' })
    expect(seenVersion(downloaded(firstSight(NOTHING_SEEN, first), now, 'F_A1.xml', null), WHOLE)).toBe('v2')
  })

  it('is seen as it is now when the person opens its XML, copies its path or opens its folder', () => {
    const now = waiting('client', 'v2', { 'F_A1.xml': 'v2' })
    const seen = firstSight(NOTHING_SEEN, first)
    expect(seenVersion(looked(seen, now, 'F_A1.xml'), WHOLE)).toBe('v2')
    expect(seenVersion(looked(seen, now), WHOLE)).toBe('v2')
  })

  it('is forgotten once confirmed: what is still on the page is not taken again, the next file is', () => {
    const after = confirmed(firstSight(NOTHING_SEEN, first), first, 'F_A1.xml')
    expect(seenVersion(after, WHOLE)).toBeNull()
    expect(seenVersion(firstSight(after, first), WHOLE)).toBeNull() // the page has not reloaded yet
    expect(seenVersion(looked(after, first, 'F_A1.xml'), WHOLE)).toBeNull() // nor does a look at it count
    expect(seenVersion(downloaded(after, first, 'F_A1.xml', 'v1'), WHOLE)).toBeNull() // nor saving it once more
    expect(seenVersion(firstSight(after, waiting('client', 'v5', { 'F_C3.xml': 'v5' })), WHOLE)).toBe('v5')
  })

  it('is forgotten the same way when all the files are confirmed from the card under the lists', () => {
    const after = confirmed(firstSight(NOTHING_SEEN, first), first)
    expect(seenVersion(firstSight(after, first), WHOLE)).toBeNull()
  })
})

describe('a file for each invoice', () => {
  const first = waiting('invoice', 'w1', { 'F_A1.xml': 'a1', 'F_A2.xml': 'b1' })
  const seenFirst = firstSight(NOTHING_SEEN, first)
  const all = (seen: typeof seenFirst) => [seenVersion(seen, 'F_A1.xml'), seenVersion(seen, 'F_A2.xml'), seenVersion(seen, WHOLE)]

  it('remembers each file by its name, and all of them together', () => {
    expect(seenKey('F_A1.xml', first)).toBe('F_A1.xml')
    expect(all(seenFirst)).toEqual(['a1', 'b1', 'w1'])
  })

  it('takes a file that appears later as it is first shown, and keeps the others', () => {
    const more = waiting('invoice', 'w2', { 'F_A1.xml': 'a2', 'F_A2.xml': 'b1', 'F_A3.xml': 'c1' })
    const seen = firstSight(seenFirst, more)
    expect([seenVersion(seen, 'F_A1.xml'), seenVersion(seen, 'F_A3.xml'), seenVersion(seen, WHOLE)]).toEqual(['a1', 'c1', 'w1'])
  })

  it('takes nothing new when nothing new is shown', () => {
    expect(firstSight(seenFirst, first)).toBe(seenFirst) // the same object: drawing settles
  })

  it('sees one file as it is now when that file is looked at, and nothing else', () => {
    // The other file was written again, unseen: confirming them all must still be refused.
    const now = waiting('invoice', 'w2', { 'F_A1.xml': 'a2', 'F_A2.xml': 'b2' })
    expect(all(looked(seenFirst, now, 'F_A1.xml'))).toEqual(['a2', 'b1', 'w1'])
  })

  it('sees every file, and all of them together, as they are now when their folder is opened', () => {
    const now = waiting('invoice', 'w2', { 'F_A1.xml': 'a2', 'F_A2.xml': 'b2' })
    expect(all(looked(seenFirst, now))).toEqual(['a2', 'b2', 'w2'])
  })

  it('sees a downloaded file as downloaded, and nothing else', () => {
    const now = waiting('invoice', 'w2', { 'F_A1.xml': 'a1', 'F_A2.xml': 'b2' })
    expect(all(downloaded(seenFirst, now, 'F_A2.xml', 'b9'))).toEqual(['a1', 'b9', 'w1'])
  })

  it('forgets one file confirmed, which is not taken again while it is still on the page', () => {
    const after = confirmed(seenFirst, first, 'F_A1.xml', { before: 'w1', after: 'w3' })
    expect(seenVersion(firstSight(after, first), 'F_A1.xml')).toBeNull()
    expect(seenVersion(after, 'F_A2.xml')).toBe('b1')
  })

  it('sees the files that are left, together, as the program has them once one is confirmed', () => {
    // The program says how all the files stood when it confirmed: as the person saw them.
    expect(all(confirmed(seenFirst, first, 'F_A1.xml', { before: 'w1', after: 'w3' }))).toEqual([null, 'b1', 'w3'])
  })

  it('keeps all of them together as they were seen when another file had changed, even unknown to the page', () => {
    // A colleague had F_A2 written again; this page still lists the older one. The program
    // says the files were not as seen: confirming them all later must be refused.
    const after = confirmed(seenFirst, first, 'F_A1.xml', { before: 'w2', after: 'w4' })
    const reloaded = firstSight(after, waiting('invoice', 'w4', { 'F_A2.xml': 'b2' }))
    expect(all(reloaded)).toEqual([null, 'b1', 'w1'])
  })

  it('keeps all of them together as they were seen when the program does not say how they stood', () => {
    expect(seenVersion(confirmed(seenFirst, first, 'F_A1.xml'), WHOLE)).toBe('w1')
  })

  it('has nothing left to see together once the last file is confirmed', () => {
    const last = waiting('invoice', 'w3', { 'F_A2.xml': 'b1' })
    const seen = confirmed(firstSight(NOTHING_SEEN, last), last, 'F_A2.xml', { before: 'w3', after: null })
    expect(seenVersion(firstSight(seen, last), WHOLE)).toBeNull() // the page has not reloaded yet
    expect(seenVersion(firstSight(seen, waiting('invoice', 'w9', { 'F_A7.xml': 'g1' })), WHOLE)).toBe('w9')
  })

  it('forgets everything when all the files are confirmed', () => {
    const after = confirmed(seenFirst, first)
    expect(firstSight(after, first)).toBe(after)
    expect(all(after)).toEqual([null, null, null])
  })
})

describe('a confirmation refused because the file changed', () => {
  const first = waiting('invoice', 'w1', { 'F_A1.xml': 'a1', 'F_A2.xml': 'b1' })
  const changed = waiting('invoice', 'w2', { 'F_A1.xml': 'a2', 'F_A2.xml': 'b1' })
  const seenFirst = firstSight(NOTHING_SEEN, first)

  it('is said on that file alone, and changes nothing of what was seen', () => {
    const after = refused(seenFirst, 'F_A1.xml')
    expect([hasChanged(after, 'F_A1.xml'), hasChanged(after, 'F_A2.xml'), hasChanged(after, WHOLE)]).toEqual([true, false, false])
    expect(seenVersion(after, 'F_A1.xml')).toBe('a1')
  })

  it('is no longer said once the person tries again', () => {
    expect(hasChanged(attempted(refused(seenFirst, 'F_A1.xml'), 'F_A1.xml'), 'F_A1.xml')).toBe(false)
  })

  it('has the file seen again as the program has it now, and only that file', () => {
    const again = seenAgain(refused(seenFirst, 'F_A1.xml'), changed, 'F_A1.xml')
    expect([seenVersion(again, 'F_A1.xml'), seenVersion(again, 'F_A2.xml'), seenVersion(again, WHOLE)]).toEqual(['a2', 'b1', 'w1'])
  })

  it('keeps that version from then on: a file written once more is refused once more', () => {
    // Refused at v2, imported at v2, then written again as v3 while the page reloads by itself.
    const one = waiting('client', 'v1', { 'F_A1.xml': 'v1' })
    const two = waiting('client', 'v2', { 'F_A1.xml': 'v2' })
    const three = waiting('client', 'v3', { 'F_A1.xml': 'v3' })
    const afterRefusal = seenAgain(refused(firstSight(firstSight(NOTHING_SEEN, one), two), WHOLE), two, 'F_A1.xml')
    // Looking at it, or not, the version kept is the one shown after the refusal.
    expect(seenVersion(looked(afterRefusal, two, 'F_A1.xml'), WHOLE)).toBe('v2')
    expect(seenVersion(firstSight(afterRefusal, three), WHOLE)).toBe('v2')
  })

  it('has the client\'s one file seen again under whatever name it has now', () => {
    const one = waiting('client', 'v1', { 'F_A1.xml': 'v1' })
    const renamed = waiting('client', 'v2', { 'F_B7.xml': 'v2' })
    const again = seenAgain(refused(firstSight(NOTHING_SEEN, one), WHOLE), renamed, 'F_A1.xml')
    expect(hasChanged(again, seenKey('F_B7.xml', renamed))).toBe(true)
    expect(seenVersion(again, WHOLE)).toBe('v2')
  })

  it('forgets a file that no longer waits', () => {
    const gone = waiting('invoice', 'w3', { 'F_A2.xml': 'b1' })
    expect(seenVersion(seenAgain(refused(seenFirst, 'F_A1.xml'), gone, 'F_A1.xml'), 'F_A1.xml')).toBeNull()
  })

  it('has every file seen again, and all of them together, when the card under the lists was refused', () => {
    const now = waiting('invoice', 'w5', { 'F_A1.xml': 'a2', 'F_A3.xml': 'c1' }) // one changed, one gone, one new
    const again = seenAgain(refused(seenFirst, WHOLE), now)
    expect([hasChanged(again, WHOLE), hasChanged(again, 'F_A1.xml')]).toEqual([true, false])
    expect([seenVersion(again, 'F_A1.xml'), seenVersion(again, 'F_A2.xml'), seenVersion(again, 'F_A3.xml'), seenVersion(again, WHOLE)])
      .toEqual(['a2', null, 'c1', 'w5'])
  })

  it('keeps what was seen again from then on, whatever the page reloads by itself', () => {
    const again = seenAgain(refused(seenFirst, WHOLE), changed)
    const later = waiting('invoice', 'w3', { 'F_A1.xml': 'a3', 'F_A2.xml': 'b2' })
    expect([seenVersion(firstSight(again, later), 'F_A1.xml'), seenVersion(firstSight(again, later), 'F_A2.xml'), seenVersion(firstSight(again, later), WHOLE)])
      .toEqual(['a2', 'b1', 'w2'])
  })
})
