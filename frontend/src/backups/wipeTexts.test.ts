import { describe, expect, it } from 'vitest'
import { ApiError } from '../api'
import type { BackupStatus } from '../types'
import { CONFIRM_WORD, confirmsWipe, wipeBlockedBecause, wipeFailure } from './wipeTexts'

const STATUS: BackupStatus = {
  folder: 'E:\\Copii AutoSaga', folder_found: true, snapshots: [], count: 0, max: 25,
  last_at: null, next_due_at: null, due_now: false, last_failure: null, last_restore: null,
}

describe('the word that confirms a wipe', () => {
  it('is STERG, typed with small or capital letters, with Ș or without', () => {
    expect(CONFIRM_WORD).toBe('STERG')
    for (const typed of ['STERG', 'sterg', 'Sterg', ' ȘTERG ', 'șterg', 'ŞTERG', 'şterg']) {
      expect(confirmsWipe(typed), typed).toBe(true)
    }
  })

  it('is nothing else', () => {
    for (const typed of ['', 'STER', 'STERGE', 'șterge', 'ST ERG', 'da', 'STERG STERG']) {
      expect(confirmsWipe(typed), typed).toBe(false)
    }
  })
})

describe('when the wipe cannot be started from the page', () => {
  it('can be started once the backup folder is chosen and at hand', () => {
    expect(wipeBlockedBecause(STATUS)).toBeNull()
  })

  it('says to choose a folder first, since the copy made before goes there', () => {
    expect(wipeBlockedBecause({ ...STATUS, folder: null, folder_found: false }))
      .toBe('Alegeți mai întâi folderul copiilor, mai sus: înainte de ștergere programul face o copie acolo.')
  })

  it('says to plug the folder back in when it is away', () => {
    expect(wipeBlockedBecause({ ...STATUS, folder_found: false }))
      .toBe('Folderul copiilor nu este la locul lui. Conectați-l, apoi puteți șterge datele.')
  })
})

describe('why nothing was deleted', () => {
  it('names what the program is busy with', () => {
    expect(wipeFailure(new ApiError('busy', 'Invoices are being downloaded or classified.')))
      .toBe('Nu s-a șters nimic. Acum programul descarcă sau clasifică facturi, se actualizează sau restaurează o copie. Așteptați să se termine, apoi încercați din nou.')
  })

  it('points at the folder when the copy could not be made or checked', () => {
    expect(wipeFailure(new ApiError('backup_error', 'Nothing was deleted. The backup folder was not found.')))
      .toBe('Nu s-a șters nimic. Copia de siguranță nu a putut fi făcută sau verificată. Verificați folderul copiilor și încercați din nou.')
  })

  it('still says nothing was deleted when the program does not answer', () => {
    expect(wipeFailure(new ApiError('unreachable', 'The program did not answer.')))
      .toMatch(/^Nu se știe dacă datele au fost șterse\. /)
  })
})
