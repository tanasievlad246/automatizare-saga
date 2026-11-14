import { errorDetail, errorMessage } from '../errorMessages'
import { Notice } from './Notice'

/**
 * A failure said inside the page: the Romanian sentence and, in small print, the program's
 * own words. The sentence for an unknown failure asks the person to show the technical
 * details to whoever helps, so they have to be here to show. `here` holds the sentences of
 * one place where a code means something more exact, as `errorMessage` takes them.
 */
export function ErrorNotice({ error, here }: { error: unknown; here?: Record<string, string> }) {
  return (
    <Notice tone="attention">
      <p>{errorMessage(error, here)}</p>
      {/* The detail may be a long path without a space: it breaks anywhere instead of spilling. */}
      <p className="text-[0.9rem] [overflow-wrap:anywhere]">Detalii tehnice: {errorDetail(error)}</p>
    </Notice>
  )
}
