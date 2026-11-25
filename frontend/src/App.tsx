import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Overview from './pages/Overview'
import YouTube from './pages/YouTube'
import TikTok from './pages/TikTok'
import Instagram from './pages/Instagram'
import Facebook from './pages/Facebook'
import Operations from './pages/Operations'
import Settings from './pages/Settings'

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="youtube" element={<YouTube />} />
        <Route path="tiktok" element={<TikTok />} />
        <Route path="instagram" element={<Instagram />} />
        <Route path="facebook" element={<Facebook />} />
        <Route path="operations" element={<Operations />} />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  )
}

export default App
