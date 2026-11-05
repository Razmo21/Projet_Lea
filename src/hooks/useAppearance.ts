import { useEffect, useState } from 'react'
import { readTheme, themeKey } from '../lib/appearance'
import type { Theme } from '../lib/appearance'

// Aucun polling : le thème est appliqué localement et synchronisé entre onglets.
export function useAppearance() {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      return readTheme(
        window.localStorage,
        window.matchMedia('(prefers-color-scheme: dark)').matches,
      )
    } catch {
      return 'light'
    }
  })
  const [themeError, setThemeError] = useState('')

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  useEffect(() => {
    // Une valeur étrangère ou corrompue ne devient jamais une classe CSS.
    function sync(event: StorageEvent) {
      if (
        event.key === themeKey &&
        (event.newValue === 'light' || event.newValue === 'dark')
      )
        setTheme(event.newValue)
    }
    window.addEventListener('storage', sync)
    return () => window.removeEventListener('storage', sync)
  }, [])

  // L'affichage reste utilisable même si le navigateur refuse la mémorisation.
  function chooseTheme(next: Theme) {
    setTheme(next)
    try {
      window.localStorage.setItem(themeKey, next)
      setThemeError('')
    } catch {
      setThemeError(
        'Thème appliqué pour cette session ; sa mémorisation est indisponible.',
      )
    }
  }

  return { theme, chooseTheme, themeError }
}
