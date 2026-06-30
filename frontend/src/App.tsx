import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Nav } from '@/components/Nav'
import { Home } from '@/pages/Home'
import { WeekendPage } from '@/pages/WeekendPage'
import { SubscribePage } from '@/pages/SubscribePage'

export default function App() {
  return (
    <BrowserRouter>
      <Nav />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/weekends/:year/:round" element={<WeekendPage />} />
        <Route path="/subscribe" element={<SubscribePage />} />
      </Routes>
    </BrowserRouter>
  )
}
