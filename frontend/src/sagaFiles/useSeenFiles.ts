import { useState } from 'react'
import { api } from '../api'
import type { WaitingFiles } from '../types'
import {
  NOTHING_SEEN, WHOLE, type Seen, type Together, attempted, confirmed, downloaded, firstSight, hasChanged, looked, refused,
  seenAgain, seenKey, seenVersion,
} from './seenFiles'

/** What one confirmation needs of what the person has seen: of one file, or of all the client's files together. */
export type SeenOf = {
  /** The version seen. Null when none is kept: then the one the page lists is sent. */
  version: string | null
  /** A confirmation was refused because it had changed. */
  changed: boolean
  /** The person looked at it as it is now: its XML, its path, its folder. */
  look: () => void
  /** A confirmation is about to be sent. */
  attempt: () => void
  /** It went through. `together`: the program's word on how all the client's files stood, with one file confirmed. */
  confirmed: (together?: Together) => void
  /** It was refused because the file had changed. */
  refused: () => void
}

/**
 * What the person has seen of one client's files for SAGA, kept for as long as the client's
 * screen is open: one owner for "Fișier importat" on each file and "Da, am importat" under the
 * lists, so a confirmation from one is known to the other. The rules are in seenFiles.ts.
 */
export function useSeenFiles(cui: string, waiting: WaitingFiles | undefined) {
  const [kept, setKept] = useState({ cui, seen: NOTHING_SEEN })
  // Another client's files are another matter: nothing of them is seen yet.
  let seen = kept.cui === cui ? kept.seen : NOTHING_SEEN
  // Taken while drawing: what is shown for the first time is what the person sees.
  if (waiting) seen = firstSight(seen, waiting)
  if (kept.cui !== cui || kept.seen !== seen) setKept({ cui, seen })

  const change = (how: (seen: Seen, now: WaitingFiles) => Seen) => {
    if (waiting) setKept((old) => (old.cui === cui ? { cui, seen: how(old.seen, waiting) } : old))
  }
  /** Of one file by its name, or with no name of all the files together. */
  const of = (name?: string): SeenOf => {
    const key = name === undefined || !waiting ? WHOLE : seenKey(name, waiting)
    return {
      version: seenVersion(seen, key),
      changed: hasChanged(seen, key),
      look: () => change((old, now) => looked(old, now, name)),
      attempt: () => change((old) => attempted(old, key)),
      confirmed: (together) => change((old, now) => confirmed(old, now, name, together)),
      refused: () => {
        change((old) => refused(old, key))
        // What the person sees next is the file as it is now: asked of the program, not taken
        // from a list the page may still hold from before. Until it answers, and if it does
        // not, what was seen stays, and another press is refused again.
        api.sagaFiles(cui).then(
          (fresh) => setKept((old) => (old.cui === cui ? { cui, seen: seenAgain(old.seen, fresh, name) } : old)),
          () => {},
        )
      },
    }
  }
  return {
    whole: of(),
    of: (name: string) => of(name),
    /** The file was saved on this computer, in the version the program gave it in. */
    downloaded: (name: string, version: string | null) => change((old, now) => downloaded(old, now, name, version)),
    /** The files were written again: what comes next is seen fresh. */
    forgetAll: () => change((old, now) => confirmed(old, now)),
  }
}
