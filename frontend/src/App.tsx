import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Nav } from '@/components/Nav'
import { Landing } from '@/pages/Landing'
import { Weekends } from '@/pages/Weekends'
import { WeekendPage } from '@/pages/WeekendPage'
import { SubscribePage } from '@/pages/SubscribePage'

export default function App() {
  return (
    <BrowserRouter>
      <Nav />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/weekends" element={<Weekends />} />
        <Route path="/weekends/:year/:round" element={<WeekendPage />} />
        <Route path="/subscribe" element={<SubscribePage />} />
      </Routes>
    </BrowserRouter>
  )
}
