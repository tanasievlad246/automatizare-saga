// What the person has seen of a client's files for SAGA. A confirmation ("Fișier importat",
// "Da, am importat") sends the version seen, not the one the page shows now: the page reloads
// by itself, and a file written again since it was taken was never imported in SAGA.

import type { WaitingFile, WaitingFiles } from '../types'

/** The key of all the client's files together: what the card under the lists confirms. */
export const WHOLE = ''

export type Seen = {
  /** By key: the version the person saw. */
  versions: Record<string, string>
  /**
   * By key: a version not to be taken as seen. It was just confirmed, and stays on the page
   * until the page reloads; what comes after it is taken.
   */
  outdated: Record<string, string>
  /** The keys whose confirmation was refused because the file had changed. */
  changed: string[]
}

export const NOTHING_SEEN: Seen = { versions: {}, outdated: {}, changed: [] }

/** What waits for the client now, as much of it as these rules read. */
export type Now = Pick<WaitingFiles, 'file_per' | 'version'> & { files: Pick<WaitingFile, 'name' | 'version'>[] }

/**
 * The key a file is remembered by. The client's one file is the same file whatever its name (it
 * is renamed when its first invoice changes), and is all the client's files; with a file for
 * each invoice, a file is known by its name.
 */
export function seenKey(name: string, now: Now): string {
  return now.file_per === 'client' && now.files.length <= 1 ? WHOLE : name
}

/** Every key with its version as the page shows it now. */
function versionsNow(now: Now): Record<string, string> {
  const versions: Record<string, string> = {}
  for (const file of now.files) versions[seenKey(file.name, now)] = file.version
  if (now.version !== null) versions[WHOLE] = now.version
  return versions
}

export function seenVersion(seen: Seen, key: string): string | null {
  return seen.versions[key] ?? null
}

export function hasChanged(seen: Seen, key: string): boolean {
  return seen.changed.includes(key)
}

/**
 * What is shown for the first time is taken as seen; what was seen already is kept, whatever
 * the page reloads. The same object when nothing is new, so it can be called while drawing.
 */
export function firstSight(seen: Seen, now: Now): Seen {
  const fresh = Object.entries(versionsNow(now)).filter(
    ([key, version]) => !(key in seen.versions) && seen.outdated[key] !== version,
  )
  return fresh.length === 0 ? seen : { ...seen, versions: { ...seen.versions, ...Object.fromEntries(fresh) } }
}

/** These keys are seen in these versions; one just confirmed, still on the page, is not seen again. */
function taken(seen: Seen, shown: Record<string, string>, keys: string[]): Seen {
  const versions = { ...seen.versions }
  for (const key of keys) {
    if (key in shown && seen.outdated[key] !== shown[key]) versions[key] = shown[key]
  }
  return { ...seen, versions }
}

/**
 * The person looked at the files as they are now. At one of them (its XML, its path, its
 * folder): that file is seen, and nothing else, so another file written again unseen still
 * refuses a confirmation of them all. With no name, at the folder with all of them: every file
 * is seen, and all of them together.
 */
export function looked(seen: Seen, now: Now, name?: string): Seen {
  const shown = versionsNow(now)
  return taken(seen, shown, name === undefined ? Object.keys(shown) : [seenKey(name, now)])
}

/**
 * The person saved the file on their computer: that copy is what they have, in the `version` the
 * program gave it in; as the page lists it, when the program said none.
 */
export function downloaded(seen: Seen, now: Now, name: string, version: string | null): Seen {
  const key = seenKey(name, now)
  return version === null ? looked(seen, now, name) : taken(seen, { [key]: version }, [key])
}

/** These keys are forgotten: what the page still shows of them is not taken again; what comes next is. */
function forgotten(seen: Seen, shown: Record<string, string>, keys: string[]): Seen {
  const versions = { ...seen.versions }
  const outdated = { ...seen.outdated }
  for (const key of keys) {
    delete versions[key]
    if (key in shown) outdated[key] = shown[key]
  }
  return { ...seen, versions, outdated }
}

/** A confirmation is about to be sent for this key: what was said of an earlier one goes. */
export function attempted(seen: Seen, key: string): Seen {
  return hasChanged(seen, key) ? { ...seen, changed: seen.changed.filter((each) => each !== key) } : seen
}

/** How all the client's files together stood when the program confirmed one of them, and how those left stand. */
export type Together = { before: string | null; after: string | null }

/**
 * An import was confirmed: of one file, or with no name of all of them. What was confirmed is
 * forgotten, so the file that comes next is seen fresh.
 *
 * With a file for each invoice, one file leaving changes all of them together. `together` is
 * the program's word on it: if the files stood as the person saw them (`before`), those left
 * are seen as the program has them now (`after`). If they did not, because another file was
 * written again, known to this page or not, the older version stays the one seen, and
 * confirming them all is refused. The same when the program does not say.
 */
export function confirmed(seen: Seen, now: Now, name?: string, together?: Together): Seen {
  const shown = versionsNow(now)
  const key = name === undefined ? WHOLE : seenKey(name, now)
  if (key === WHOLE) return { ...forgotten(seen, shown, [...Object.keys(seen.versions), ...Object.keys(shown)]), changed: [] }
  const after = attempted(forgotten(seen, shown, [key]), key)
  if (!together || together.before === null || seen.versions[WHOLE] !== together.before) return after
  return together.after === null
    ? forgotten(after, shown, [WHOLE]) // nothing is left; what the page still lists is not seen again
    : { ...after, versions: { ...after.versions, [WHOLE]: together.after } }
}

/**
 * A confirmation of this key was refused because the file had changed: it is said there. What
 * was seen stays as it was until the program says how the file is now (seenAgain), so a press
 * in between is refused again.
 */
export function refused(seen: Seen, key: string): Seen {
  return hasChanged(seen, key) ? seen : { ...seen, changed: [...seen.changed, key] }
}

/**
 * After a refusal, with what waits now as the program has just given it (`fresh`), not as the
 * page may still list it: the person is shown the file as it is, so that is what they see from
 * here on, and the version kept. One file refused: that file. The card under the lists refused
 * (no name): every file, and all of them together. A file that no longer waits is forgotten.
 */
export function seenAgain(seen: Seen, fresh: Now, name?: string): Seen {
  const shown = versionsNow(fresh)
  const keys = name === undefined ? [...Object.keys(seen.versions), ...Object.keys(shown)] : [seenKey(name, fresh)]
  const versions = { ...seen.versions }
  const outdated = { ...seen.outdated }
  for (const key of keys) {
    delete outdated[key]
    if (key in shown) versions[key] = shown[key]
    else delete versions[key]
  }
  return { ...seen, versions, outdated }
}
