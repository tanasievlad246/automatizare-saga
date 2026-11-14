import { Link } from 'react-router'

/** The product's mark and name, at the left of the top bar. Pressing it goes to the first screen. */
export function Brand() {
  return (
    // Never squeezed: in a top bar kept on one row it is the SAGA folder that gives way.
    <Link to="/" className="flex items-center gap-3 text-foreground no-underline min-[60rem]:shrink-0">
      <span aria-hidden className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground">
        {/* An invoice with an arrow going in: what the program does. */}
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M6 3.5h8l4 4V20.5H6z" />
          <path d="M9 13h6M12.5 10.5L15 13l-2.5 2.5" />
        </svg>
      </span>
      <span className="flex flex-col leading-tight">
        <span className="font-heading text-[1.3rem] font-bold">AutoSaga</span>
        <span className="text-[0.8rem] text-muted-foreground">e-Factura în SAGA, automat</span>
      </span>
    </Link>
  )
}
