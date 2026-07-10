import { useState, type FormEvent } from 'react'
import { BlurFade } from '@/components/BlurFade'
import { apiPost } from '@/lib/api'

type Status = 'idle' | 'submitting' | 'done' | 'error'

export function SubscribePage() {
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState<Status>('idle')

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setStatus('submitting')
    try {
      const res = await apiPost<{ status: string }>('/subscribe', { email })
      setStatus(res.status ? 'done' : 'error')
    } catch {
      setStatus('error')
    }
  }

  return (
    // Outer container matches every other page so the heading's left edge lines up
    // sitewide; the lg cap keeps the form itself at a comfortable reading width.
    <main className="mx-auto max-w-[1312px] px-6 py-24">
      <div className="max-w-lg">
      <BlurFade>
        <p className="kicker text-accent">The digest</p>
        <h1 className="mt-4 font-display text-6xl leading-[0.95] tracking-tight">
          telo<span className="text-accent">gify</span> your weekend
        </h1>
        <p className="mt-4 text-lg text-muted">
          Three insights per race weekend, speeding to your inbox.
        </p>
      </BlurFade>

      {status === 'done' ? (
        <BlurFade>
          <p className="glass lift mt-12 rounded-[--radius-panel] p-6 text-ink">
            You are on the list. Watch for the next digest.
          </p>
        </BlurFade>
      ) : (
        <BlurFade delay={0.06}>
          <form onSubmit={onSubmit} className="mt-12 space-y-5">
            <div>
              <label htmlFor="email" className="kicker mb-2 block text-muted">
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full rounded-[--radius-panel] border-[1.5px] border-ink bg-surface px-4 py-3 text-ink outline-none transition-shadow placeholder:text-muted focus:shadow-[3px_3px_0_var(--color-accent)]"
              />
            </div>
            <button
              type="submit"
              disabled={status === 'submitting'}
              className="lift w-full rounded-[--radius-panel] border-[1.5px] border-ink bg-accent px-4 py-3 font-semibold uppercase tracking-wider text-accent-ink shadow-[4px_4px_0_var(--color-shadow)] disabled:opacity-60"
            >
              {status === 'submitting' ? 'Subscribing...' : 'Subscribe'}
            </button>
            {status === 'error' && (
              <p className="text-sm text-accent" role="alert">Something went wrong. Try again.</p>
            )}
          </form>
        </BlurFade>
      )}
      </div>
    </main>
  )
}
