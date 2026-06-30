import { useState, type FormEvent } from 'react'
import { BlurFade } from '@/components/BlurFade'
import { apiPost } from '@/lib/api'

type Status = 'idle' | 'submitting' | 'done' | 'error'

export function SubscribePage() {
  const [email, setEmail] = useState('')
  const [constructor, setConstructor] = useState('')
  const [status, setStatus] = useState<Status>('idle')

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setStatus('submitting')
    try {
      const res = await apiPost<{ status: string }>('/subscribe', {
        email,
        followed_constructor: constructor || null,
      })
      setStatus(res.status ? 'done' : 'error')
    } catch {
      setStatus('error')
    }
  }

  return (
    <main className="mx-auto max-w-md px-6 py-24">
      <BlurFade>
        <h1 className="text-4xl font-semibold tracking-tight">
          Let&apos;s telo<span className="text-accent">gify</span> this weekend
        </h1>
        <p className="mt-3 text-muted">
          The post-race digest: three telemetry insights, in your inbox.
        </p>
      </BlurFade>

      {status === 'done' ? (
        <BlurFade>
          <p className="mt-10 glass rounded-[--radius-panel] p-6 text-ink">
            You are on the list. Watch for the next digest.
          </p>
        </BlurFade>
      ) : (
        <BlurFade delay={0.06}>
          <form onSubmit={onSubmit} className="mt-10 space-y-5">
            <div>
              <label htmlFor="email" className="mb-2 block text-sm text-muted">
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full rounded-xl border border-border bg-surface px-4 py-3 text-ink outline-none transition-colors placeholder:text-muted focus:border-accent"
              />
            </div>
            <div>
              <label htmlFor="constructor" className="mb-2 block text-sm text-muted">
                Favourite constructor <span className="text-muted/70">(optional)</span>
              </label>
              <input
                id="constructor"
                type="text"
                value={constructor}
                onChange={(e) => setConstructor(e.target.value)}
                placeholder="McLaren"
                className="w-full rounded-xl border border-border bg-surface px-4 py-3 text-ink outline-none transition-colors placeholder:text-muted focus:border-accent"
              />
            </div>
            <button
              type="submit"
              disabled={status === 'submitting'}
              className="w-full rounded-xl bg-accent px-4 py-3 font-medium text-accent-ink transition-opacity hover:opacity-90 disabled:opacity-60"
            >
              {status === 'submitting' ? 'Subscribing...' : 'Subscribe'}
            </button>
            {status === 'error' && (
              <p className="text-sm text-accent">Something went wrong. Try again.</p>
            )}
          </form>
        </BlurFade>
      )}
    </main>
  )
}
