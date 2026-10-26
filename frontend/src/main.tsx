import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { BusinessApp } from './BusinessApp';
import './style.css';
createRoot(document.getElementById('root')!).render(<StrictMode>{window.location.pathname === '/workspace' ? <BusinessApp /> : <App />}</StrictMode>);
