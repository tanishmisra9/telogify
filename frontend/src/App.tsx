import { LazyMotion, domAnimation } from 'framer-motion'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Nav } from '@/components/Nav'
import { Landing } from '@/pages/Landing'
import { Weekends } from '@/pages/Weekends'
import { WeekendPage } from '@/pages/WeekendPage'
import { SubscribePage } from '@/pages/SubscribePage'

// LazyMotion + the slim `m` components load only the DOM animation feature set
// (~4.6kb vs ~34kb for full `motion`); we use no layout/drag animations.
export default function App() {
  return (
    <LazyMotion features={domAnimation}>
      <BrowserRouter>
        <Nav />
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/weekends" element={<Weekends />} />
          <Route path="/weekends/:year/:round" element={<WeekendPage />} />
          <Route path="/subscribe" element={<SubscribePage />} />
        </Routes>
      </BrowserRouter>
    </LazyMotion>
  )
}
