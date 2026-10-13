import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// Apply the persisted theme before first paint to avoid a flash.
const storedTheme = window.localStorage.getItem('pth-theme')
document.documentElement.setAttribute(
  'data-theme',
  storedTheme === 'light' ? 'light' : 'dark',
)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
