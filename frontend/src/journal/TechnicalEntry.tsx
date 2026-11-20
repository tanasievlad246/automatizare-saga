import { useQuery } from '@tanstack/react-query'
import { Check, ChevronDown, ChevronRight, Copy } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { toast } from 'sonner'
import { ErrorNotice } from '@/components/ErrorNotice'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { api } from '../api'
import { COPY_REFUSED, copyText } from '../clipboard'
import type { TechnicalBody, TechnicalExchange, TechnicalRecord, TechnicalWhole } from '../types'
import { formatDuration } from './eventTexts'
import { bodyNote, clockFine, readableBody, recordLevelName, shortAddress, statusLook } from './technical'

const STATUS_LOOKS = {
  ok: 'bg-done text-done-foreground',
  limited: 'bg-attention text-attention-foreground',
  failed: 'bg-destructive/15 text-destructive',
}

/**
 * One request to ANAF or Jev, or one record of the program, among the steps of an operation.
 * Opened, it reads the whole record: what was sent and what came back, or the exception.
 */
export function TechnicalEntry({ record }: { record: TechnicalRecord }) {
  const [open, setOpen] = useState(false)
  const Arrow = open ? ChevronDown : ChevronRight
  return (
    <div className="border-t bg-[#fbfcfd] px-4.5 py-2.5">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex w-full cursor-pointer flex-wrap items-baseline gap-x-3.5 gap-y-1.5 text-left outline-none focus-visible:ring-3 focus-visible:ring-ring"
      >
        <Arrow aria-hidden className="size-4.5 shrink-0 self-center text-muted-foreground" />
        <span className="shrink-0 text-muted-foreground tabular-nums">{clockFine(record.at)}</span>
        {record.kind === 'http' ? <RequestHead record={record} /> : <ProgramHead record={record} />}
      </button>
      {open && <TechnicalDetails record={record} />}
    </div>
  )
}

function RequestHead({ record }: { record: TechnicalRecord }) {
  return (
    <>
      <Badge className="min-w-[6.5rem] shrink-0 justify-center bg-accent text-accent-foreground">Cerere</Badge>
      <span className="w-14 shrink-0 font-mono text-[0.94rem] font-bold">{record.method}</span>
      <span className={cn('shrink-0 rounded-md px-2 font-mono text-[0.88rem] font-bold', STATUS_LOOKS[statusLook(record)])}>
        {record.status ?? 'fără răspuns'}
      </span>
      {record.duration_ms !== null && record.duration_ms !== undefined && (
        <span className="w-16 shrink-0 text-[0.94rem] text-muted-foreground tabular-nums">{formatDuration(record.duration_ms)}</span>
      )}
      {/* A small basis keeps the address on the row; it breaks anywhere, having no spaces. */}
      <span className="min-w-0 flex-[1_1_200px] font-mono text-[0.88rem] [overflow-wrap:anywhere]">{shortAddress(record.url ?? '')}</span>
    </>
  )
}

function ProgramHead({ record }: { record: TechnicalRecord }) {
  return (
    <>
      <Badge className="min-w-[6.5rem] shrink-0 justify-center bg-muted text-foreground">Program</Badge>
      <span className="w-40 shrink-0 font-mono text-[0.88rem] text-muted-foreground [overflow-wrap:anywhere]">
        {recordLevelName(record.level)} · {record.where}
      </span>
      <span className="min-w-0 flex-[1_1_200px] font-mono text-[0.88rem] [overflow-wrap:anywhere]">{record.summary}</span>
    </>
  )
}

function TechnicalDetails({ record }: { record: TechnicalRecord }) {
  const whole = useQuery({ queryKey: ['journal-technical-record', record.id], queryFn: () => api.technicalRecord(record.id) })
  return (
    // Under the row's text in a wide window; the whole width on a phone, where every column counts.
    <div className="mt-2.5 text-[0.94rem] sm:ml-8">
      {whole.isPending && <p role="status" className="text-muted-foreground">Se încarcă…</p>}
      {whole.error && <ErrorNotice error={whole.error} />}
      {whole.data && (record.kind === 'http' ? <Exchange record={whole.data.record} /> : <ProgramRecord record={whole.data.record} />)}
    </div>
  )
}

/** What was sent and what came back, side by side; one above the other in a narrow window. */
function Exchange({ record }: { record: TechnicalWhole }) {
  const { request, response } = record.body
  const known = record.duration_ms !== null && record.duration_ms !== undefined
  const took = known ? `, în ${formatDuration(record.duration_ms!)}` : ''
  const waited = known ? ` după ${formatDuration(record.duration_ms!)}` : ''
  return (
    <div className="grid gap-3.5 md:grid-cols-2">
      <Half title="Ce s-a trimis">
        <Headers pairs={[['Adresa', `${record.method} ${record.url}`], ...(request?.headers ?? [])]} />
        {request && <Body body={request.body} />}
      </Half>
      <Half title={response ? `Ce s-a primit: codul ${record.status}${took}` : `Nu a primit răspuns${waited}`}>
        {response ? <Answer response={response} /> : <p className="rounded-lg bg-background px-3 py-2.5 font-mono text-[0.88rem]">{record.error}</p>}
      </Half>
    </div>
  )
}

function Answer({ response }: { response: TechnicalExchange }) {
  return (
    <>
      <Headers pairs={response.headers} />
      <Body body={response.body} />
    </>
  )
}

function Half({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex min-w-0 flex-col gap-2.5 rounded-xl border bg-card px-3 py-3 sm:px-3.5">
      <h3 className="font-sans text-base font-bold">{title}</h3>
      {children}
    </section>
  )
}

function Headers({ pairs }: { pairs: [string, string][] }) {
  if (!pairs.length) return null
  return (
    <dl className="grid grid-cols-[max-content_minmax(0,1fr)] gap-x-3 gap-y-0.5 font-mono text-[0.82rem] [overflow-wrap:anywhere]">
      {pairs.map(([name, value], index) => (
        <div key={index} className="contents">
          <dt className="text-muted-foreground">{name}</dt>
          <dd className={value === '[hidden]' ? 'w-fit rounded bg-muted px-1' : ''}>{value}</dd>
        </div>
      ))}
    </dl>
  )
}

/** A body as it was kept: laid out to be read, with a button that copies it. */
function Body({ body }: { body: TechnicalBody }) {
  if (!('text' in body)) return <p className="rounded-lg bg-background px-3 py-2.5">{bodyNote(body)}</p>
  const shown = readableBody(body)
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2.5">
        <span className="text-muted-foreground">{bodyNote(body)}</span>
        <CopyButton text={shown} />
      </div>
      <pre className="max-h-72 overflow-auto rounded-lg bg-secondary p-3 font-mono text-[0.8rem] leading-relaxed break-all whitespace-pre-wrap text-secondary-foreground">
        {shown}
      </pre>
    </>
  )
}

function ProgramRecord({ record }: { record: TechnicalWhole }) {
  return (
    <div className="flex flex-col gap-2 rounded-lg bg-background px-3.5 py-3">
      <p className="font-mono text-[0.88rem] [overflow-wrap:anywhere]">
        {record.where} · {record.function} · {record.logger}
      </p>
      {record.body.exception ? (
        <pre className="max-h-64 overflow-auto rounded-md bg-card p-3 font-mono text-[0.82rem] whitespace-pre-wrap">{record.body.exception}</pre>
      ) : (
        <p className="text-muted-foreground">Fără excepție.</p>
      )}
    </div>
  )
}

/** Copies the body as it is shown. The word changes to "Copiat" for two seconds. */
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (!copied) return
    const timer = setTimeout(() => setCopied(false), 2000)
    return () => clearTimeout(timer)
  }, [copied])
  const copy = () =>
    copyText(text).then(
      () => setCopied(true),
      () => toast.error('Conținutul nu a fost copiat.', { description: COPY_REFUSED, duration: Infinity }),
    )
  return (
    <>
      <Button variant="outline" size="sm" onClick={copy}>
        {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
        {/* Both words take the same place, so the button keeps its width. */}
        <span className="grid">
          <span className={`col-start-1 row-start-1 ${copied ? 'invisible' : ''}`}>Copiază conținutul</span>
          <span className={`col-start-1 row-start-1 ${copied ? '' : 'invisible'}`}>Copiat</span>
        </span>
      </Button>
      <span role="status" className="sr-only">{copied ? 'Copiat' : ''}</span>
    </>
  )
}
