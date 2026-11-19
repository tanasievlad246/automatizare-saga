// The words of "Ștergerea tuturor datelor", kept apart from the window so they can be tested.

import { ApiError } from '../api'
import type { BackupStatus } from '../types'

/** What the person types to confirm. Without diacritics, so any keyboard can type it. */
export const CONFIRM_WORD = 'STERG'

/**
 * Whether the typed word confirms the wipe: STERG with small or capital letters, with Ș
 * (comma or cedilla) or a plain S, and spaces around it forgiven. Nothing else does, so a
 * click made in a hurry is never enough.
 */
export function confirmsWipe(typed: string): boolean {
  const plain = typed.trim().normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase()
  return plain === CONFIRM_WORD
}

/**
 * Why the button on the page cannot be pressed, or null when it can. The copy made before
 * the wipe goes to the backup folder, so without the folder there is no wipe.
 */
export function wipeBlockedBecause(status: BackupStatus): string | null {
  if (!status.folder) return 'Alegeți mai întâi folderul copiilor, mai sus: înainte de ștergere programul face o copie acolo.'
  if (!status.folder_found) return 'Folderul copiilor nu este la locul lui. Conectați-l, apoi puteți șterge datele.'
  return null
}

/**
 * The sentence for a wipe that did not happen. The program refuses before deleting anything,
 * and says so, for every reason it knows of; with no answer at all, whether it got as far as
 * deleting is not known, and the sentence says how to find out.
 */
export function wipeFailure(error: unknown): string {
  const code = error instanceof ApiError ? error.code : ''
  if (code === 'busy') {
    return 'Nu s-a șters nimic. Acum programul descarcă sau clasifică facturi, se actualizează sau restaurează o copie. Așteptați să se termine, apoi încercați din nou.'
  }
  if (code === 'backup_error') {
    return 'Nu s-a șters nimic. Copia de siguranță nu a putut fi făcută sau verificată. Verificați folderul copiilor și încercați din nou.'
  }
  return 'Nu se știe dacă datele au fost șterse. Încărcați pagina din nou și uitați-vă în lista copiilor: dacă a apărut o copie „făcută înainte de ștergerea datelor”, ștergerea s-a făcut.'
}
