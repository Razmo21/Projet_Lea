export type Theme = 'light' | 'dark'
export const themeKey = 'lea.appearance.theme'

// Cette préférence visuelle appartient à l'interface, pas aux réglages IA SQLite.
export function readTheme(
  storage: Pick<Storage, 'getItem'>,
  prefersDark: boolean,
): Theme {
  try {
    const saved = storage.getItem(themeKey)
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    /* Le stockage peut être désactivé par le navigateur. */
  }
  return prefersDark ? 'dark' : 'light'
}
