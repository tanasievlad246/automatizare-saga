import { useMutation } from '@tanstack/react-query'
import { CodeXml } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { api } from '../api'
import { COPY_REFUSED, copyText } from '../clipboard'
import { showError } from '../errorMessages'
import { formatWhen } from '../format'
import type { Invoice, WaitingFile } from '../types'
import { opensWindowsHere, pathOnThisPC, useWhere } from '../where'
import { FileInvoicesTable } from './FileInvoicesTable'
import { FileXmlDialog } from './FileXmlDialog'
import { FILES_TAB, fileSummary } from './waitingFiles'

/**
 * One file waiting for SAGA: its name, where it is, when it was written, how many invoices it
 * holds and what they are worth, its XML in a window, and its invoices in a table. `onLook`: the
 * person opened its XML, copied its path or opened its folder, so they have the file as it is now.
 */
export function WaitingFileCard({
  cui, file, invoices, onLook,
}: { cui: string; file: WaitingFile; invoices: Invoice[]; onLook: () => void }) {
  const [showingXml, setShowingXml] = useState(false)
  // By one of its invoices: the folder the file is really in.
  const openFolder = useMutation({ mutationFn: () => api.openFolderOf(file.ids[0]), onError: showError })
  const where = useWhere()
  const path = pathOnThisPC(file.path, where) // as this computer reaches it
  const summary = fileSummary(invoices, file.invoices)
  const showXml = () => {
    onLook()
    setShowingXml(true)
  }
  const showFolder = () => {
    onLook()
    openFolder.mutate()
  }
  const copyPath = () => {
    onLook()
    return copyText(path).then(
      () => toast.success('Calea a fost copiată.'),
      () => toast.error('Calea nu a fost copiată.', { description: COPY_REFUSED, duration: Infinity }),
    )
  }

  return (
    <li className="flex flex-col gap-3 rounded-2xl border bg-card px-5 py-4.5">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h3 className="min-w-0 font-mono text-[1.02rem] font-bold break-all">{file.name}</h3>
        {file.written_at && <span className="text-muted-foreground sm:ml-auto">Scris: {formatWhen(file.written_at)}</span>}
      </div>
      <p className="rounded-lg bg-background px-3.5 py-3 font-mono text-[0.88rem] break-all">{path}</p>
      {!file.present && <p className="font-semibold text-attention-foreground">{FILES_TAB.missing}</p>}
      <div>
        <p>
          <strong>{summary.count}</strong>
          {summary.total && <> · Total <strong>{summary.total}</strong></>}
        </p>
        {summary.kinds && <p className="text-[0.9rem] text-muted-foreground">{summary.kinds}</p>}
      </div>
      {/* Named with their file: the same buttons repeat on every card. */}
      <div className="flex flex-wrap gap-2.5">
        {file.present && (
          <Button variant="outline" size="sm" aria-label={`${FILES_TAB.xmlButton}: ${file.name}`} onClick={showXml}>
            <CodeXml aria-hidden />
            {FILES_TAB.xmlButton}
          </Button>
        )}
        <Button variant="outline" size="sm" aria-label={`Copiază calea: ${file.name}`} onClick={copyPath}>Copiază calea</Button>
        {opensWindowsHere(where) && (
          <Button
            variant="outline" size="sm" aria-label={`Deschide folderul: ${file.name}`}
            disabled={openFolder.isPending || file.ids.length === 0} onClick={showFolder}
          >
            Deschide folderul
          </Button>
        )}
      </div>
      {invoices.length > 0 && <FileInvoicesTable fileName={file.name} memory={`${cui}/${file.name}`} invoices={invoices} />}
      {showingXml && (
        <FileXmlDialog cui={cui} file={file} summary={summary.count.toLowerCase()} onClose={() => setShowingXml(false)} />
      )}
    </li>
  )
}
