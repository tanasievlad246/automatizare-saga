/** In the top bar of a demo: a reminder that nothing on the page is real. */
export function DemoLabel() {
  return (
    <span
      title="Clienții și facturile sunt inventate. Nimic nu vine de la ANAF și nimic nu se plătește lui Jev."
      className="flex min-h-9 items-center rounded-full border border-attention-border bg-attention px-3.5 text-sm font-semibold whitespace-nowrap text-attention-foreground"
    >
      Date de probă
    </span>
  )
}
