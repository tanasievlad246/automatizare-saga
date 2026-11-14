import { errorDetail, errorMessage } from '../errorMessages'
import { Notice } from './Notice'

/**
 * A failure said inside the page: the Romanian sentence and, in small print, the program's
 * own words. The sentence for an unknown failure asks the person to show the technical
 * details to whoever helps, so they have to be here to show.
 */
export function ErrorNotice({ error }: { error: unknown }) {
  return (
    <Notice tone="attention">
      <p>{errorMessage(error)}</p>
      {/* The detail may be a long path without a space: it breaks anywhere instead of spilling. */}
      <p className="text-[0.9rem] [overflow-wrap:anywhere]">Detalii tehnice: {errorDetail(error)}</p>
    </Notice>
  )
}
