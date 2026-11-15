import { useEffect, useState } from 'react'

/** The current moment, renewed every minute (or `every` milliseconds) while the screen is open. */
export function useNow(every = 60_000): Date {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), every)
    return () => clearInterval(timer)
  }, [every])
  return now
}
