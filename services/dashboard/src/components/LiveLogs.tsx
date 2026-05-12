import { useEffect, useRef, useState } from 'react'
import clsx from 'clsx'

export interface LogLine {
  ts: string
  level: 'info' | 'warn' | 'error' | 'debug' | 'stdout'
  text: string
  source?: string
}

interface Props {
  lines: LogLine[]
  maxLines?: number
  className?: string
  autoScroll?: boolean
}

const LEVEL_COLOR: Record<string, string> = {
  error:  'text-rvp-error',
  warn:   'text-rvp-warning',
  info:   'text-rvp-info',
  debug:  'text-gray-500',
  stdout: 'text-gray-300',
}

export function LiveLogs({ lines, maxLines = 500, className, autoScroll = true }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const [pinned, setPinned] = useState(autoScroll)

  const visible = lines.slice(-maxLines)

  useEffect(() => {
    if (pinned) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [visible.length, pinned])

  return (
    <div className={clsx('relative font-mono text-xs', className)}>
      <div
        className="h-full overflow-y-auto bg-rvp-bg rounded-lg p-3 space-y-px"
        onScroll={(e) => {
          const el = e.currentTarget
          const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40
          setPinned(atBottom)
        }}
      >
        {visible.map((line, i) => (
          <div key={i} className="flex gap-2 leading-5">
            <span className="text-gray-600 shrink-0 select-none">
              {new Date(line.ts).toLocaleTimeString()}
            </span>
            {line.source && (
              <span className="text-gray-500 shrink-0">[{line.source}]</span>
            )}
            <span className={clsx('break-all', LEVEL_COLOR[line.level] ?? 'text-gray-300')}>
              {line.text}
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      {!pinned && (
        <button
          onClick={() => { setPinned(true); bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }}
          className="absolute bottom-3 right-4 btn-ghost text-xs py-1"
        >
          ↓ scroll to bottom
        </button>
      )}
    </div>
  )
}
