import { useQuery } from '@tanstack/react-query'
import { Notice } from '@/components/Notice'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ApiError, api } from '../api'
import { errorMessage } from '../errorMessages'
import { formatWhen } from '../format'
import { XmlViewer } from '../invoices/XmlViewer'
import type { WaitingFile } from '../types'
import { FILES_TAB } from './waitingFiles'

/** One file waiting for SAGA, exactly as it is in the client's folder now, laid out to be read and copied. */
export function FileXmlDialog({ cui, file, summary, onClose }: { cui: string; file: WaitingFile; summary: string; onClose: () => void }) {
  const { data: xml, error } = useQuery({
    // Under "invoices", so whatever changes an invoice has the file read again; and by when it was written.
    queryKey: ['invoices', cui, 'saga-file-xml', file.name, file.written_at],
    queryFn: () => api.sagaFileXml(cui, file.name),
  })
  const gone = error instanceof ApiError && error.code === 'not_found'

  return (
    <Dialog open onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle className="font-heading text-2xl break-all">{file.name}</DialogTitle>
          <DialogDescription className="text-base">
            {summary}
            {file.written_at && ` · Scris: ${formatWhen(file.written_at)}`}
          </DialogDescription>
        </DialogHeader>
        {error ? (
          <Notice tone="attention">{gone ? FILES_TAB.xmlGone : errorMessage(error)}</Notice>
        ) : xml === undefined ? (
          <p role="status" className="text-muted-foreground">Se încarcă fișierul…</p>
        ) : (
          <XmlViewer xml={xml} inWindow explanation={FILES_TAB.xmlExplanation} whenMissing={FILES_TAB.xmlGone} />
        )}
        <DialogFooter>
          <Button variant="outline" size="lg" onClick={onClose}>Închide</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
