const paths = {
  plus: 'M12 5v14M5 12h14',
  close: 'm6 6 12 12M6 18 18 6',
  settings: 'M4 7h16M4 17h16M9 4v6M15 14v6',
  send: 'M12 19V5m-6 6 6-6 6 6',
  mic: 'M9 5a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0zM6 10v2a6 6 0 0 0 12 0v-2M12 18v4m-4 0h8',
  voice: 'M4 10v4m4-8v12m4-15v18m4-15v12m4-8v4',
  pencil: 'm14 5 5 5M4 20l5-1L20 8a2 2 0 0 0-5-5L4 14z',
  trash: 'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7',
  stop: 'M6 6h12v12H6z',
  ephemeral:
    'M8 3H6a3 3 0 0 0-3 3v2m0 4v3a3 3 0 0 0 3 3v3l4-3m4 0h4a3 3 0 0 0 3-3v-3m0-4V6a3 3 0 0 0-3-3h-2M8 10h8',
} as const

// Icônes locales décoratives : chaque commande conserve son libellé accessible.
export default function Icon({ name }: { name: keyof typeof paths }) {
  return (
    <svg
      className="icon"
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  )
}
