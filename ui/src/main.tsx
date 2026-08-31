import { createRoot } from 'react-dom/client'
import { App } from './app/App'
import './styles.css'

const root = document.getElementById('app')
if (!root) throw new Error('JARVIS app root is missing')
createRoot(root).render(<App />)
