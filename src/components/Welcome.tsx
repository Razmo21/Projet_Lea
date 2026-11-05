export const welcomePhrases = [
  "Comment puis-je vous aider aujourd'hui ?",
  'Que puis-je faire pour vous ?',
  'Une question, une idée, un projet ?',
  "Qu'avez-vous en tête aujourd'hui ?",
  'Par quoi souhaitez-vous commencer ?',
  'Prêt à donner vie à vos idées ?',
] as const

const programmingPhrases = [
  'Quel projet allons-nous faire avancer ?',
  'Un bug à corriger, une idée à coder ?',
  'Quelle fonctionnalité souhaitez-vous créer ?',
  'Quel code souhaitez-vous explorer ?',
  'Quelle tâche puis-je réaliser dans votre projet ?',
] as const

const veterinaryPhrases = [
  'Quel sujet vétérinaire souhaitez-vous explorer ?',
  'Un cas clinique à étudier ensemble ?',
  'Quelle espèce vous intéresse aujourd’hui ?',
  'Une question de soins ou de santé animale ?',
  'Quelle notion vétérinaire souhaitez-vous approfondir ?',
] as const

// Les profils futurs gardent l'accueil général tant qu'aucune liste ne leur est dédiée.
export function welcomePhrasesForProfile(profileId?: string): readonly string[] {
  if (profileId === 'development') return programmingPhrases
  if (profileId === 'veterinary') return veterinaryPhrases
  return welcomePhrases
}

// Choisit un autre titre sans répétition immédiate ; aucune préférence n'est enregistrée.
export function nextWelcomeIndex(current: number, count: number = welcomePhrases.length): number {
  return (
    (current + 1 + Math.floor(Math.random() * (count - 1))) % count
  )
}

// Un choix à chaque nouvel accueil, jamais de minuteur ni de rotation pendant la lecture.
export default function Welcome({
  ephemeral,
  index,
  profileId,
}: {
  ephemeral: boolean
  index: number
  profileId?: string
}) {
  const phrases = welcomePhrasesForProfile(profileId)
  return (
    <div className="welcome">
      <h2 key={ephemeral ? 'ephemeral' : `${profileId}:${index}`}>
        {ephemeral ? 'Chat éphémère' : phrases[index % phrases.length]}
      </h2>
    </div>
  )
}
