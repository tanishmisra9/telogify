import { motion, useReducedMotion } from 'framer-motion'

function App() {
  const reduce = useReducedMotion()

  return (
    <main className="min-h-svh grid place-items-center px-6">
      <motion.div
        initial={reduce ? false : { opacity: 0, filter: 'blur(12px)', y: 12 }}
        animate={{ opacity: 1, filter: 'blur(0px)', y: 0 }}
        transition={{ type: 'spring', stiffness: 120, damping: 18 }}
        className="text-center"
      >
        <h1 className="text-6xl font-semibold tracking-tight">
          Telo<span className="text-accent">gify</span>
        </h1>
        <p className="mt-4 text-muted text-lg">
          Three quantified telemetry insights per race weekend.
        </p>
        <p className="mt-8 num text-sm text-muted">
          design tokens online · <span className="text-accent">amber</span> ·{' '}
          <span className="text-ink">330.5 km/h</span>
        </p>
      </motion.div>
    </main>
  )
}

export default App
