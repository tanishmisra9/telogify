import { LazyMotion, domAnimation } from 'framer-motion'
import { useEffect } from 'react'
import { BrowserRouter, Route, Routes, useLocation } from 'react-router-dom'
import { Footer } from '@/components/Footer'
import { Nav } from '@/components/Nav'
import { Landing } from '@/pages/Landing'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { Weekends } from '@/pages/Weekends'
import { WeekendPage } from '@/pages/WeekendPage'
import { SeasonPage } from '@/pages/SeasonPage'
import { SubscribePage } from '@/pages/SubscribePage'

// Route changes keep the previous scroll offset by default; reset to the top so a weekend
// clicked from partway down the list opens at its heading, not mid-page.
function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])
  return null
}

// LazyMotion + the slim `m` components load only the DOM animation feature set
// (~4.6kb vs ~34kb for full `motion`); we use no layout/drag animations.
export default function App() {
  return (
    <LazyMotion features={domAnimation}>
      <BrowserRouter>
        <ScrollToTop />
        {/* Min-height flex column so short pages still push the footer to the viewport bottom. */}
        <div className="flex min-h-dvh flex-col">
          <Nav />
          <div className="flex-1">
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/weekends" element={<Weekends />} />
              <Route path="/weekends/:year/:round" element={<WeekendPage />} />
              <Route path="/season" element={<SeasonPage />} />
              <Route path="/season/:year" element={<SeasonPage />} />
              <Route path="/subscribe" element={<SubscribePage />} />
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </div>
          <Footer />
        </div>
      </BrowserRouter>
    </LazyMotion>
  )
}
