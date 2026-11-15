"use client"

import * as React from "react"
import { cn } from "cn"
import { Switch as SwitchPrimitive } from "radix-ui"

function Switch({
  className,
  ...props
}: React.ComponentProps<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      className={cn(
        "peer relative inline-flex h-7.5 w-13 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent bg-muted-foreground/40 transition-colors outline-none after:absolute after:-inset-x-1 after:-inset-y-2 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 data-checked:bg-done-foreground",
        className
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className="pointer-events-none block size-6 translate-x-0 rounded-full bg-white shadow-sm transition-transform data-checked:translate-x-[22px]"
      />
    </SwitchPrimitive.Root>
  )
}

export { Switch }
