// The program explains failures in English, for the log. The screen says them in Romanian,
// in words that tell the person what to do next.

import { toast } from 'sonner'
import { ApiError } from './api'

const MESSAGES: Record<string, string> = {
  login_needed: 'Trebuie să vă conectați din nou la ANAF. Apăsați pe conectarea la ANAF, în bara de sus a programului.',
  login_code_expired: 'Adresa lipită a expirat sau a mai fost folosită. Începeți conectarea din nou.',
  invalid_cui: 'CUI-ul nu este corect. Verificați cifrele.',
  invalid_input: 'Ceva din ce ați completat nu este corect. Verificați și încercați din nou.',
  no_spv_rights: 'Certificatul nu are drepturi în SPV pentru această firmă.',
  anaf_limit_reached: 'ANAF a limitat numărul de cereri pentru azi. Încercați mâine.',
  login_refused: 'ANAF nu a acceptat certificatul. Verificați că este certificatul cu care intrați în SPV și că nu a expirat.',
  login_cancelled: 'Nu a fost ales niciun certificat.',
  anaf_error: 'ANAF a răspuns cu o eroare. Încercați din nou puțin mai târziu.',
  network_error: 'Nu am putut ajunge la ANAF. Verificați conexiunea la internet.',
  not_found: 'Nu am găsit ce ați cerut. Poate a fost șters între timp.',
  client_off: 'Clientul este oprit. Porniți-l din lista de clienți ca să îi descărcați facturile.',
  busy: 'Se descarcă deja facturi. Așteptați să se termine, apoi încercați din nou.',
  config_error: 'Lipsește o setare. Verificați pagina „Chei și parole”.',
  not_classifiable: 'Contul nu se poate schimba cât timp factura este bifată ca importată în SAGA. Debifați „Am importat factura în SAGA”.',
  update_error: 'Programul nu a putut fi actualizat. A rămas la versiunea pe care o avea.',
  backup_error: 'Copia de siguranță nu a reușit. Verificați folderul ales pentru copii.',
  jev_error: 'Jev nu a putut fi întrebat. Verificați cheia OpenRouter și creditul din cont.',
  unauthorized: 'Pagina nu mai are voie să vorbească cu programul. Închideți pagina și porniți programul din nou.',
  unreachable: 'Programul nu răspunde. Faceți dublu clic pe „AutoSaga” de pe Desktop, apoi încercați din nou.',
}
const UNKNOWN = 'A apărut o problemă în program. Încercați din nou. Dacă se repetă, arătați „Detaliile tehnice” celui care vă ajută.'

/**
 * The Romanian sentence for a failure. `here` holds the sentences of one place where a
 * code means something more exact than it does everywhere else.
 */
export function errorMessage(error: unknown, here: Record<string, string> = {}): string {
  return (error instanceof ApiError && (here[error.code] ?? MESSAGES[error.code])) || UNKNOWN
}

/** The sentence for a failure's code alone; the general one for a code not known here. */
export function messageForCode(code: string): string {
  return MESSAGES[code] ?? UNKNOWN
}

/** The program's own words about a failure, for whoever helps the person. */
export function errorDetail(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

/** Show a failure as a notice: the Romanian sentence, with the original kept as detail. */
export function showError(error: unknown): void {
  // It stays until closed: a message that leaves by itself after four seconds is not read.
  toast.error(errorMessage(error), { description: `Detalii tehnice: ${errorDetail(error)}`, duration: Infinity })
}
