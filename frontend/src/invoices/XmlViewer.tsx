import { Check, Copy } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { COPY_REFUSED, copyText } from '../clipboard'
import { COPY_XML, readableXml } from './readableXml'

/**
 * An XML file, laid out one element per line, with a button that copies it exactly as it is on disk.
 * `inWindow`: shown in a window, which has its own margins and must keep its buttons in sight.
 */
export function XmlViewer({
  xml, explanation, whenMissing, inWindow = false,
}: { xml: string | null; explanation: string; whenMissing: string; inWindow?: boolean }) {
  if (!xml) return <p className={cn('text-muted-foreground', !inWindow && 'px-6 py-6')}>{whenMissing}</p>
  return (
    <div className={cn('min-w-0', !inWindow && 'px-6 pt-5 pb-6')}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <p className="min-w-0 flex-[1_1_240px] text-muted-foreground">{explanation}</p>
        <CopyXmlButton xml={xml} />
      </div>
      <XmlText xml={xml} className={inWindow ? 'max-h-[52dvh]' : 'max-h-[70vh]'} />
    </div>
  )
}

/** The file as it came, not as it is laid out here: it may be pasted into a validator. */
function CopyXmlButton({ xml }: { xml: string }) {
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (!copied) return
    const timer = setTimeout(() => setCopied(false), 2000)
    return () => clearTimeout(timer)
  }, [copied])
  const copy = () =>
    copyText(xml).then(
      () => setCopied(true),
      () => toast.error(COPY_XML.refused, { description: COPY_REFUSED, duration: Infinity }),
    )

  return (
    <>
      <Button variant="outline" size="sm" onClick={copy}>
        {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
        {/* Both words take the same place, so the button keeps its width while it says "Copiat". */}
        <span className="grid">
          <span className={`col-start-1 row-start-1 ${copied ? 'invisible' : ''}`}>{COPY_XML.button}</span>
          <span className={`col-start-1 row-start-1 ${copied ? '' : 'invisible'}`}>{COPY_XML.copied}</span>
        </span>
      </Button>
      <span role="status" className="sr-only">{copied ? COPY_XML.copied : ''}</span>
    </>
  )
}

/**
 * Each line wraps under its own start, not at the left edge, so a long one still shows where it belongs.
 * It wraps right at the edge, even inside a word: breaking at a space instead would leave a line
 * that starts with spaces and a long namespace nearly empty.
 */
function XmlText({ xml, className }: { xml: string; className: string }) {
  const lines = useMemo(() => readableXml(xml).split('\n'), [xml])
  return (
    <pre className={cn('overflow-auto rounded-xl bg-secondary p-4 font-mono text-[0.82rem] leading-relaxed break-all whitespace-pre-wrap text-secondary-foreground', className)}>
      {lines.map((line, index) => {
        const indent = /^ */.exec(line)?.[0].length ?? 0
        return (
          <span key={index} className="block min-h-[1lh]" style={{ paddingLeft: `${indent}ch`, textIndent: `-${indent}ch` }}>
            {line}
          </span>
        )
      })}
    </pre>
  )
}
