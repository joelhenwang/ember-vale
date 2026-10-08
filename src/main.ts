import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'

/* Bundled fonts (no CDN — the app must work fully offline in production).
   Latin and Latin Extended only: the other subsets (Cyrillic, Greek,
   Vietnamese) were 40-odd @font-face rules in the main stylesheet that the
   game never asked for. EB Garamond is gone: it was only ever a fallback
   behind the bundled Libron and Cormorant, so it was declared but never
   drawn (perf-frontend-001). */
import '@fontsource/cormorant-garamond/latin-500.css'
import '@fontsource/cormorant-garamond/latin-ext-500.css'
import '@fontsource/cormorant-garamond/latin-600.css'
import '@fontsource/cormorant-garamond/latin-ext-600.css'
import '@fontsource/cormorant-garamond/latin-700.css'
import '@fontsource/cormorant-garamond/latin-ext-700.css'
import '@fontsource/alegreya-sans/latin-400.css'
import '@fontsource/alegreya-sans/latin-ext-400.css'
import '@fontsource/alegreya-sans/latin-500.css'
import '@fontsource/alegreya-sans/latin-ext-500.css'
import '@fontsource/alegreya-sans/latin-700.css'
import '@fontsource/alegreya-sans/latin-ext-700.css'

import './style.css'
import './styles/studio.css'
import './styles/motion.css'
import { installMotion } from './composables/useMotion'

installMotion()
createApp(App).use(router).mount('#app')
