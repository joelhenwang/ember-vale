import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'

/* Bundled fonts (no CDN — the app must work fully offline in production). */
import '@fontsource/eb-garamond/400.css'
import '@fontsource/eb-garamond/500.css'
import '@fontsource/eb-garamond/600.css'
import '@fontsource/eb-garamond/700.css'
import '@fontsource/eb-garamond/400-italic.css'
import '@fontsource/eb-garamond/500-italic.css'
import '@fontsource/cormorant-garamond/500.css'
import '@fontsource/cormorant-garamond/600.css'
import '@fontsource/cormorant-garamond/700.css'

import './style.css'
import './styles/studio.css'

createApp(App).use(router).mount('#app')
