// Libellés d'affichage seulement : les erreurs API, codes et diagnostics restent intacts.
// Chaque entrée garde le problème ou l'action utile, sans transformer un échec en succès.
const noticeLabels: Record<string, string> = {
  'Surveillance indisponible ou en attente ; l’état des ressources n’est pas confirmé.': 'Surveillance indisponible',
  'Mesure de RAM indisponible.': 'Mesure RAM indisponible',
  'Mesure CPU en attente ou indisponible.': 'Mesure CPU indisponible',
  'Charge CPU élevée persistante.': 'CPU très sollicité',
  'Marge VRAM faible persistante.': 'VRAM disponible faible',
  'Docker est indisponible ; ouvre Docker Desktop manuellement.': 'Ouvrez Docker Desktop',
  'Le modèle actif ne répond pas ; son état est incertain.': 'Le modèle ne répond pas',
  'Un service indispensable au run ne répond plus. Vérifie le run avant toute nouvelle action.': 'Vérifiez la tâche avant de continuer',
  'Préférence de ressources indisponible. Ouvre les paramètres pour la vérifier.': 'Vérifiez les paramètres de ressources',
  'Thème appliqué pour cette session ; sa mémorisation est indisponible.': 'Thème non mémorisé',
  'Le contrôleur local a renvoyé un état invalide.': 'État de Léa inconnu',
  'Le contrôleur local ne peut pas lire l’état de Léa.': 'État de Léa indisponible',
  'Une opération sur le cœur de Léa est déjà en cours.': 'Léa est déjà occupée',
  'Le runtime du profil a signalé une erreur.': 'Le modèle a rencontré une erreur',
  'La vérification du runtime est indisponible.': 'État du modèle indisponible',
  'Le modèle local de Léa n’est pas disponible.': 'Modèle local indisponible',
  'Le modèle local de Léa n’a pas fourni de réponse exploitable.': 'Aucune réponse exploitable',
  'Le modèle local de Léa a renvoyé une erreur.': 'Le modèle a rencontré une erreur',
  'La réponse du modèle local a été tronquée.': 'Réponse incomplète',
  "Le flux du modèle local s'est fermé avant la fin de la réponse.": 'Réponse interrompue',
  'Le budget du contexte local ne peut pas être vérifié.': 'Capacité du modèle non vérifiée',
  'Le message est trop grand pour la fenêtre de contexte active.': 'Message trop long',
  'Le contexte transmis au modèle local dépasse sa fenêtre disponible.': 'Contexte trop long pour le modèle',
  'L’autorisation Web est absente, expirée ou déjà utilisée. Confirme la demande à nouveau.': 'Autorisez une nouvelle recherche Web',
  "Tous les fournisseurs de recherche autorisés sont indisponibles ou ont refusé la requête. Aucun résultat n'a été inventé ; réessaie plus tard.": 'Moteurs de recherche indisponibles',
  'La page demande une authentification ou un défi externe. Aucun contournement n’a été tenté.': 'Page protégée inaccessible',
  'Le PDF ne contient aucun texte exploitable. Aucun OCR n’est exécuté.': 'Aucun texte lisible dans ce PDF',
  'Le nom de la destination Web n’a pas pu être résolu. Vérifie la connexion Internet locale.': 'Adresse Web introuvable',
  "Le fournisseur Web secondaire a présenté une protection externe. Aucun contournement n'a été tenté.": 'Moteur de recherche bloqué',
  'Le moteur de recherche a présenté une protection externe. Aucun contournement n’a été tenté.': 'Moteur de recherche bloqué',
  'Connexion à la destination Web impossible depuis Léa. Vérifie la connexion Internet locale puis réessaie.': 'Connexion au site impossible',
  'La destination Web a bloqué ou limité la requête. Aucun contournement n’a été tenté.': 'Accès refusé par le site',
  'Aucune source publique sûre et exploitable n’a été trouvée pour vérifier l’affirmation.': 'Aucune preuve Web exploitable',
  'Les extraits Web ne tiennent pas dans le contexte local actif. Reformule la demande.': 'Recherche trop large pour le modèle',
  'La réponse a été interrompue.': 'Réponse interrompue',
  'Génération interrompue.': 'Réponse interrompue',
  'Échec de la génération.': 'La réponse a échoué',
  'Le profil Programmation a échoué et le profil précédent n’a pas pu être restauré.': 'Changement de modèle échoué sans retour au précédent',
  'Le profil direct a échoué et le retour Programmation n’a pas pu être confirmé.': 'Retour au modèle précédent non confirmé',
  'Le statut du run OpenHands est invalide.': 'État de la tâche invalide',
  'Le statut du run OpenHands est indisponible.': 'État de la tâche indisponible',
  'Le profil Programmation nécessite Docker Desktop. Démarre Docker puis réessaie.': 'Ouvrez Docker Desktop',
  'Un run attend un arrêt vérifié. Vérifie Docker puis redémarre Léa.': 'Arrêt non confirmé à vérifier dans Docker',
  'Arrêt non confirmé. Vérifie Docker puis redémarre Léa pour récupérer ce run.': 'Arrêt non confirmé à vérifier dans Docker',
  'Le run OpenHands ne peut pas être arrêté en sécurité.': 'Arrêt de la tâche non confirmé',
  "L'annulation attend encore l'arrêt vérifié du run OpenHands.": 'Arrêt de la tâche non confirmé',
  'Le délai maximal du run est dépassé ; le serveur a été arrêté.': 'Tâche arrêtée après dépassement du délai',
  'Suivi OpenHands indisponible. Vérifie le run dans l’interface classique avant toute nouvelle demande.': 'Vérifiez la tâche avant de continuer',
  'Run terminé sans validation réelle : les changements ne peuvent pas être acceptés.': 'Changements non validés et non acceptables',
  'La validation du run a échoué.': 'Validation de la tâche échouée',
  'Validation du run en attente.': 'Validation en attente',
  'OpenHands a signalé une erreur d’exécution.': 'Erreur pendant la tâche',
  'L’Agent Server OpenHands ne peut pas être arrêté en sécurité.': 'Arrêt de la tâche non confirmé',
  'Le projet figé du checkpoint a changé ; restauration refusée pour éviter un écrasement.': 'Restauration refusée car le projet a changé',
  'Le projet a changé après le run ; rollback refusé pour éviter un écrasement.': 'Restauration refusée car le projet a changé',
  'Le projet a changé pendant le rollback ; restauration refusée pour éviter un écrasement.': 'Restauration refusée car le projet a changé',
  'Un lien ou reparse point est apparu pendant le rollback ; restauration refusée.': 'Restauration refusée à cause d’un lien',
  'La restauration de checkpoint est incomplète.': 'Restauration incomplète',
  'Chargez Programmation pour ouvrir cette conversation.': 'Chargez Programmation pour ouvrir cette conversation',
  'Le chat éphémère a été fermé ; la réponse est abandonnée.': 'Chat éphémère fermé',
  'Le chat éphémère a été effacé. Ouvre une nouvelle session.': 'Ouvrez un nouveau chat éphémère',
  'La conversation a changé dans une autre fenêtre. Son état actuel a été rechargé.': 'Conversation actualisée après une modification externe',
  'Le profil a changé. Ouvre un nouveau chat éphémère.': 'Ouvrez un nouveau chat éphémère',
  'Le profil ou le projet a changé. Recommence l’intervention.': 'Profil ou projet modifié',
  'Le profil a changé. Recommence l’intervention.': 'Profil modifié',
  'Le contrôleur local est indisponible. Rechargez pour vérifier les paramètres enregistrés.': 'Paramètres indisponibles',
  'Le contrôleur local n’a pas confirmé les paramètres. Rechargez pour vérifier leur état.': 'Paramètres non confirmés',
  'La confirmation ne correspond pas au choix envoyé. Rechargez les paramètres.': 'Rechargez les paramètres pour vérifier vos choix',
  'Les paramètres ont changé dans un autre onglet. Rechargez-les avant de valider.': 'Paramètres modifiés dans un autre onglet',
  'État des moteurs vocaux indisponible. Aucun moteur n’a été démarré.': 'État des voix indisponible',
  'Impossible de lister les microphones : vérifie le branchement et l’autorisation du navigateur.': 'Vérifiez le microphone et son autorisation',
  'Capture microphone indisponible dans ce navigateur.': 'Microphone indisponible dans ce navigateur',
  'Microphone sélectionné absent. Vérifie les paramètres.': 'Microphone sélectionné absent',
  'Limite de 120 secondes atteinte. Enregistrement annulé, rien envoyé.': 'Enregistrement annulé après deux minutes',
  'Finalisation audio interrompue après 3 secondes. Rien envoyé.': 'Enregistrement non terminé',
  'Enregistrement trop court. Parle au moins une seconde avant de terminer.': 'Parlez au moins une seconde',
  'Lecture bloquée par le navigateur. Réactive la sortie audio.': 'Réactivez la sortie audio',
  'Moteur vocal indisponible. Vérifie son installation locale.': 'Moteur vocal indisponible',
  'Le moteur local n’a pas produit de transcription exploitable.': 'Aucune transcription exploitable',
  'Le format audio attendu est WAV mono 16 kHz, 16 bits.': 'Format audio incompatible',
  'Contexte modifié : audio annulé. Vérifie l’historique si une demande avait déjà été envoyée.': 'Audio annulé après changement de contexte',
  'Failed to fetch': 'Connexion à Léa impossible',
  'Load failed': 'Connexion à Léa impossible',
  'NetworkError when attempting to fetch resource.': 'Connexion à Léa impossible',
  'Permission denied': 'Autorisation refusée',
}

// Préfixes précis des diagnostics dont la suite contient des valeurs variables.
// Aucun classement vague par mot-clé ni découpage qui pourrait supprimer une négation.
const diagnosticLabels: readonly (readonly [string, string])[] = [
  ['Ce navigateur ne peut pas décoder l’enregistrement, avant envoi à Whisper.', 'Essayez le microphone dans Microsoft Edge'],
  ['Décodage audio impossible dans le navigateur', 'Essayez le microphone dans Microsoft Edge'],
  ['Le contexte préparé dépasse', 'Contexte trop long pour le modèle'],
  ['Des sources Web ont été collectées, mais le modèle local', 'Synthèse Web impossible'],
  ['Je ne peux pas analyser le contenu de cette vidéo : la plateforme ne fournit aucun texte public exploitable.', 'Aucun texte public pour analyser cette vidéo'],
  ["OpenHands ou le modèle a signalé une erreur d'exécution.", 'Erreur pendant la tâche'],
  ['OpenHands a terminé techniquement, mais ses preuves de session sont incomplètes.', 'Preuves de la tâche incomplètes'],
  ["OpenHands a terminé techniquement, mais aucune action terminal ou file_editor réussie n'a été observée.", 'Aucune action réussie vérifiée'],
  ['OpenHands a terminé techniquement sans FinishTool final vérifiable.', 'Fin de tâche non vérifiée'],
  ['OpenHands a terminé techniquement avec une réponse finale interne ou non exploitable.', 'Aucune réponse finale exploitable'],
  ['OpenHands a terminé techniquement alors que sa réponse finale annonçait encore une action à faire.', 'Tâche non terminée'],
  ['OpenHands a terminé techniquement après une erreur file_editor sans relecture et nouvelle tentative vérifiables.', 'Modification de fichier non validée'],
  ['OpenHands a terminé techniquement, mais aucune validation demandée avec code de sortie 0', 'Aucun test réussi après la dernière modification'],
  ['OpenHands a été arrêté après une boucle de remplacements file_editor', 'Tâche arrêtée après des modifications répétées'],
  ['OpenHands a tenté un remplacement source sans changement réel.', 'Aucune modification réelle effectuée'],
  ['OpenHands a tenté une commande terminal interdite, qui a été bloquée avant exécution.', 'Commande interdite bloquée'],
  ['Une recherche Web échouée exige une nouvelle autorisation.', 'Autorisez une nouvelle recherche Web'],
  ['Une recherche Web échouée doit être renvoyée', 'Autorisez une nouvelle recherche Web'],
  ['Une demande Web modifiée doit être envoyée', 'Autorisez une nouvelle recherche Web'],
  ['Une réponse Web ne peut pas être régénérée sans nouvelle autorisation.', 'Autorisez une nouvelle recherche Web'],
  ['Démarrage du cœur de Léa a échoué.', 'Démarrage de Léa échoué'],
  ['Arrêt du cœur de Léa a échoué.', 'Arrêt de Léa non confirmé'],
]

// Les replis restent neutres quand aucun diagnostic connu ne décrit précisément l'erreur.
const noticeFallbacks = {
  action: 'Cette action est impossible',
  core: 'Un problème empêche Léa de fonctionner',
  model: 'Un problème affecte le modèle',
  project: 'Un problème affecte le projet',
  task: 'Un problème affecte la tâche',
  conversation: 'Un problème affecte la conversation',
  preferences: 'Les paramètres ne sont pas confirmés',
  voice: 'Un problème affecte l’audio',
  resources: 'État des ressources non confirmé',
} as const

// Raccourcit seulement les notifications de l'application, jamais le texte d'une conversation.
export function shortNotice(
  message: string | null | undefined,
  context: keyof typeof noticeFallbacks = 'action',
): string {
  const text = message?.trim() ?? ''
  if (!text) return ''
  const known = Object.hasOwn(noticeLabels, text)
    ? noticeLabels[text]
    : diagnosticLabels.find(([prefix]) => text.startsWith(prefix))?.[1]
  if (known) return known

  // Les libellés déjà brefs restent fidèles. Un diagnostic inconnu n'est pas tronqué.
  const phrase = text.replace(/[.!…]+$/, '')
  if (phrase.length > 0 && phrase.length <= 80 && phrase.split(/\s+/).length <= 12 && !/[;\r\n.!?]/.test(phrase)) {
    return phrase
  }
  return noticeFallbacks[context]
}
