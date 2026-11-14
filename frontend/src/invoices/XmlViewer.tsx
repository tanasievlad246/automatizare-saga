/** An XML file as text, exactly as it is on disk. */
export function XmlViewer({ xml, explanation, whenMissing }: { xml: string | null; explanation: string; whenMissing: string }) {
  if (!xml) return <p className="px-6 py-6 text-muted-foreground">{whenMissing}</p>
  return (
    <div className="px-6 pt-5 pb-6">
      <p className="mb-3 text-muted-foreground">{explanation}</p>
      <pre className="max-h-[70vh] overflow-auto rounded-xl bg-secondary p-4 font-mono text-[0.82rem] leading-relaxed text-secondary-foreground">
        {xml}
      </pre>
    </div>
  )
}
