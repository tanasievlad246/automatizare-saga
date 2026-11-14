import type { ReactNode } from 'react'

/** The heading of a screen, with one plain sentence saying what the screen is for. */
export function PageTitle({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div>
      <h1 className="text-[2rem] leading-tight">{title}</h1>
      {children && <p className="mt-2 max-w-3xl text-lg text-muted-foreground">{children}</p>}
    </div>
  )
}
