# TODO — Projet Léa

## Étapes terminées

- [x] Étape 1 — Interface localhost minimale.
- [x] Étape 2 — Backend FastAPI minimal.
- [x] Étape 3 — Connexion frontend / backend avec réponse fictive.
- [x] Étape 4 — Installation et test du premier modèle local.
- [x] Étape 5 — Première vraie réponse de Léa : frontend React, FastAPI et modèle local reliés et validés.

## ÉTAPE 6 — Démarrage et arrêt local — terminée

- [x] Créer une commande locale unique pour démarrer Léa.
- [x] Suivre uniquement les processus lancés par Léa.
- [x] Vérifier l’état des trois composants.
- [x] Arrêter proprement les processus et nettoyer l’état temporaire.
- [x] Vérifier deux cycles complets de démarrage et d’arrêt.

## ÉTAPE 7 — Raisonnement, contrôle local et contexte temporaire — terminée

- [x] Utiliser le raisonnement équilibré et ne jamais afficher la pensée interne.
- [x] Permettre le démarrage et l’arrêt local du cœur depuis l’interface.
- [x] Ajouter un contexte de conversation temporaire en mémoire vive seulement.
- [x] Réduire l’historique par paires complètes dans la fenêtre de contexte.

## ÉTAPE 8 — Conversations locales persistantes et fiables — terminée

- [x] Désactiver le raisonnement visible avec une directive interne jamais persistée.
- [x] Utiliser une fenêtre de contexte de 8 192 tokens et un seul slot modèle.
- [x] Ajouter SQLite avec migrations, WAL, clés étrangères et contraintes.
- [x] Faire du backend l’unique autorité de l’historique du modèle.
- [x] Persister, lister, rechercher, ouvrir, renommer et supprimer les conversations.
- [x] Gérer les échecs, interruptions et réessais sans faux message assistant.
- [x] Modifier et régénérer de façon destructive, sans branche implicite.
- [x] Protéger les écritures par révision et sérialiser les générations d’une conversation.
- [x] Valider les migrations, l’API, le contexte, l’interface et Microsoft Edge Stable.
- [x] Vérifier directement l’intégrité et le contenu de la base SQLite.

## ÉTAPE 9 — Mémoire générale explicite — terminée

- [x] Ajouter les migrations SQLite pour `memories` et sa provenance
  informative `memory_sources`.
- [x] Reconnaître les commandes explicites de mémorisation et d’oubli.
- [x] Normaliser les faits sans rapprochement sémantique et éviter les doublons.
- [x] Mémoriser ou oublier atomiquement sans appeler le modèle.
- [x] Injecter tous les souvenirs actifs comme données JSON dans le budget 8 192.
- [x] Exclure les tours de gestion mémoire du contexte tout en les conservant visibles.
- [x] Préserver les souvenirs globaux lors de la suppression d’une conversation
  et les supprimer uniquement par une commande explicite `Oublie que`.
- [x] Valider migrations, concurrence, capacité, modèle réel et Microsoft Edge Stable.

## ÉTAPE 10 — Multi-modèles et profil Programmation — terminée

Configuration Programmation validée : `Qwen2.5-Coder-7B-Instruct Q6_K`,
22 000 tokens, un slot, `llama.cpp` b10516 (`b95502ba9`) et OpenHands SDK /
Agent Server 1.43.1 minimal, sans Agent Canvas pendant les runs. Docker Desktop
reste un prérequis démarré manuellement.

- [x] 10A — Contrat global de fiabilité et anti-hallucination commun aux profils.
- [x] 10B — Registre modèles/profils unique et cohérent.
- [x] 10C — Profil Programmation local et disponibilité OpenHands vérifiable.
- [x] 10D — Commutation sûre Général ↔ Programmation avec rollback.
- [x] 10E — Sélecteur frontend des profils sans rechargement de conversation.
- [x] 10F — Projets confinés exactement à `L:\IA_WORKSPACE`.
- [x] 10G — Intégration agentique OpenHands : lecture, édition, terminal et annulation.
- [x] 10H — Checkpoints, consultation des changements, acceptation et rollback avec conflit.
- [x] 10I — Persistance SQLite compacte des runs, sessions et checkpoints.
- [x] 10J — Validation finale, sécurité minimale et non-régressions.

## ÉTAPE 11 — Architecture indépendante des modèles — terminée

- [x] 11A — Auditer les dépendances aux modèles, moteurs et lanceurs existants.
- [x] 11B — Centraliser le registre validé et supprimer les parseurs concurrents.
- [x] 11C — Séparer les modèles des contrats, permissions et budgets des profils.
- [x] 11D — Isoler le protocole et les arguments llama.cpp dans un adaptateur simple.
- [x] 11E — Conserver le cycle de vie sûr et adapter les consommateurs OpenHands.
- [x] 11F — Valider résolution, erreurs, sécurité, non-régressions et vrais modèles.
- [x] 11G — Relire, commenter, nettoyer les doublons prouvés et documenter.
- [x] Validation manuelle confirmée par l’utilisateur dans l’autorisation de l’étape 12.

Preuves réelles : Général, historique, mémoire explicite après redémarrage,
commutation, deux petits runs OpenHands validés, rollback exact et Accept.
Substitution/partage de modèle validés en configuration de test, sans nouveau
GGUF. Aucun benchmark difficile relancé, aucun mécanisme de récupération ajouté.

## ÉTAPE 12 — Centre de paramètres de Léa — terminée

- [x] 12A — Audit du cycle de vie et de la persistance existants.
- [x] 12B — Préférences SQLite indépendantes, migration additive et contrôle local hors IA.
- [x] 12C — Page dédiée, navigation préservée, validation explicite et erreurs visibles.
- [x] 12D — Général Low par défaut / High, directives réellement testées et filtrage privé.
- [x] 12E — Audit Programmation : aucun contrôle fictif ; comportement OpenHands conservé.
- [x] 12F — Conflits, corruptions, indisponibilité et sauvegardes pendant génération/run.
- [x] 12G — Extension localisée démontrée par une colonne de test, sans réglage futur livré.
- [x] 12H — Edge, vrais modèles, run OpenHands validé, rollback et persistance après reprise.
- [x] 12I — Relecture, commentaires, documentation et ménage ciblé.
- [x] 12J — Non-régression complète et clôture technique sans commit/push.
- [x] Validation manuelle confirmée par l’utilisateur dans l’autorisation de l’étape 13.

Programmation : aucun mécanisme Low/High suffisamment fiable n’a été établi
avec Qwen2.5-Coder. Pas de faux High par défaut ni de réduction des protections.
Le choix d’une éventuelle stratégie agentique distincte est reporté, sans bloquer
le centre de paramètres.

## ÉTAPE 13 — Programmation avancée — terminée

- [x] 13A — Audit KEEP / IMPROVE / ADD / REMOVE et périmètre confirmé.
- [x] 13B — Timeout parent, identité du résultat, erreurs publiques sûres, arrêt confirmé.
- [x] 13C — Reprise fail-closed, slot bloqué si incertain, panne réelle puis Rollback exact.
- [x] 13D — Surveillance native RAM/CPU, NVIDIA et disponibilité locale, coût mesuré.
- [x] 13E — Hystérésis, alertes indépendantes, diagramme facultatif, préférence SQLite 9.
- [x] Complément 13D/E — Surveillance commune à tous les profils actifs, sondes
  Docker réservées à OpenHands ; encadré « Votre question » réutilisant le style existant.
- [x] 13F — Choix utilisateur appliqué : applications manuelles, conteneur au seul lancement du run.
- [x] 13G — Barrière examinée ; report de l’automatisation Edge approuvé, aucune capacité livrée.
- [x] 13H — Audit : propriétaires existants suffisants, aucun pont Windows arbitraire.
- [x] 13I — Suppression du seul conteneur arrêté/validé vérifié, sans volume ni prune.
- [x] 13J — Général, mémoire, historique, OpenHands, Accept, panne/Rollback et UI réels.
- [x] 13K — Relecture, commentaires, nettoyage ciblé et documentation.
- [x] 13L — Suites complètes, clôture technique, aucun commit/push.
- [x] Validation manuelle et finalisation confirmées par le prompt de l’étape 14.

Preuves et limites : `docs/ETAPE_13_VALIDATION.md`. Qwen et les politiques
d’outils restent inchangés. Edge agentique non livré ; Docker Desktop manuel.
La demande explicite de l’étape 14 autorise uniquement le périmètre vocal ci-dessous.

## ÉTAPE 14 — Microphone et conversation vocale — terminée

Le prompt 14 remplace le périmètre initial « Entrées multimodales » par la voix
seule, sans renuméroter la suite. Accord de téléchargement obtenu (10 Go maximum),
installation CPU isolée effectuée. Décisions D-030 à D-032 et preuves détaillées :
`docs/ETAPE_14_VALIDATION.md`. Les essais synthétiques restent distingués de la
validation physique finalement confirmée par l’utilisateur.

- [x] 14A — Whisper Small Q5_1/Piper SIWIS CPU, accord et mesures.
- [x] 14B — Capture explicite, bornée, annulable et nettoyée ; périphérique synthétique testé.
- [x] 14C — Dictée dans le brouillon, sans écrasement/envoi, également cœur arrêté.
- [x] 14D — Interface vocale dédiée sans contenu textuel des échanges.
- [x] 14E — Échanges deux clics, sériels, sans écoute automatique ; Général et retour d’échec Programmation testés.
- [x] 14F — TTS français local, lecture navigateur, interruption et écoute physique validées.
- [x] 14G — Historique existant, aucun doublon ni conservation audio automatique.
- [x] 14H — Retour vocal réel failed/Rollback ; run écrit validated/Accept ; règles inchangées.
- [x] 14I — Préférences réelles validées, volume/High persistés après arrêt complet.
- [x] 14J — Mesures moteurs RAM/VRAM/CPU/latence avec les deux profils, limites documentées.
- [x] 14K — Suites et essais intégrés documentés, échecs Qwen distingués des tests réussis.
- [x] Diagnostic du décodage : Opus refusé dans VS Code intégré, comparaison identique réussie dans Edge ; message explicite et tests de finalisation partagés.
- [x] Pocket TTS `french` intégré comme « Léa — Voix naturelle française » par défaut ; Piper/SIWIS conservé et sélection persistante migrée.
- [x] 14L — Bilan, nettoyage et validation physique/manuelle utilisateur terminés ; banc d’essai externe supprimé après contrôle.
- [x] Maintenance finale — workspace vidé par l’utilisateur puis vérifié vide,
  mémoire de test supprimée après sauvegarde, SQLite compacté et suppression
  des conversations durcie par `secure_delete`.
- [x] Audit final — 151 fichiers inventoriés, deux imports inutiles retirés,
  suites complètes et cycle local réel isolé réussis sans commencer l’étape 15.

## ÉTAPE 15 — Vétérinaire et optimisation des contrats — validation manuelle requise

- [x] Modèle local `Qwen3.5-9B-Q4_K_M`, empreinte et compatibilité llama.cpp vérifiés.
- [x] Troisième profil direct sans Web, vision, outil ni accès workspace.
- [x] Contexte 16 384, un slot, ressources mesurées et commutations sûres entre les trois profils.
- [x] Low/High Vétérinaire natif, indépendant de Général ; migration SQLite 12 et paramètres persistants.
- [x] Conversations, suppression, historique, mémoire explicite, surveillance et voix réutilisés.
- [x] Scénarios vétérinaires comparés avec corrigé indépendant et erreurs scientifiques documentées.
- [x] Contrat commun audité puis conservé intact après échec des tests de sécurité ; Général, mémoire et Vétérinaire clarifiés.
- [x] Tentative de raccourcissement Programmation annulée après régression réelle `file_editor`.
- [x] Runs OpenHands isolés : succès de référence, échecs détectés et rollbacks exacts, aucune heuristique Qwen ajoutée.
- [x] Rapport technique : `docs/ETAPE_15_VALIDATION.md`.
- [ ] Validation manuelle dans Microsoft Edge autonome.

## ÉTAPE 16 — Accès Web — terminée et validée manuellement

- [x] Web Gateway backend partagé par Général, Programmation et Vétérinaire.
- [x] Préférence SQLite 13 désactivée par défaut et accord manuel par requête.
- [x] Confirmation conservatrice des demandes ambiguës et permission à usage unique.
- [x] Recherche gratuite DuckDuckGo Lite et lecture de pages HTML publiques simples.
- [x] DNS épinglé, filtrage SSRF/redirections, limites de temps, taille et nombre de sources.
- [x] Pages traitées comme données non fiables, sans historique ni souvenir transmis.
- [x] Sources cliquables persistées sans conserver les pages HTML complètes.
- [x] Indicateur, erreurs et annulation Web dans l’interface ; voix explicite partagée.
- [x] Tests simulés, suites de non-régression, build et essai fournisseur réel.
- [x] Correctif manuel 16.1 : texte explicite aligné avec le bouton, termes utiles
  extraits sans modèle, parseur `<meta>` robuste et erreurs Web différenciées.
- [x] Correctif de fiabilité 16.1 : DuckDuckGo prioritaire, un secours Bing borné,
  fournisseur réellement cité, migration 14 pour l’origine des erreurs et garde-fou
  ciblé sur les informations actuelles sans recherche automatique.
- [x] Requête utile condensée avant l'unique essai primaire ; nouvel accord et
  nouveau brouillon obligatoires après tout échec Web.
- [x] Correctif « informations actuelles sans Web » : tournure météo française
  reconnue et réponse backend déterministe, sans appel modèle ni réseau.
- [x] Phase 16.1 techniquement acceptée ; validation manuelle complète reportée
  à la fin de l’étape 16 sur décision de l’utilisateur.
- [x] Phase 16.2 — jusqu’à trois recherches complémentaires et quatre sources
  par défaut, pertinence minimale, origines/copies distinctes et verdict prudent.
- [x] Dates de publication, mise à jour, document et consultation distinguées ;
  citations `[S…]` attribuées et validées par le backend avant persistance.
- [x] PDF publics textuels lus en RAM sous limites d’octets, pages, texte et
  décompression ; aucun OCR, temporaire persistant ni contenu actif.
- [x] Descriptions, métadonnées et transcriptions vidéo publiques exploitées
  seulement lorsqu’elles existent, sans prétendre visionner une vidéo.
- [x] Tests déterministes 16.2, non-régression 16.1 et vérifications Internet
  réelles documentés dans `docs/ETAPE_16_2_VALIDATION.md`.
- [x] Correctif de fiabilité 16.2 : dates éditoriales exclues des appuis
  d’événement, passages datés rapprochés, verdicts positifs/contradictoires
  rattachés à deux citations lues ou remplacés par une conclusion prudente.
- [x] Correctifs de validation manuelle : confirmation `Oui, vas-y` rattachée
  au message, au profil et à la révision exacts ; aucun envoi de la confirmation
  seule au modèle, réutilisation ou mélange de sujets.
- [x] Faux outils et revendications de sources refusés hors collecte ; anciens
  tours exclus de la synthèse Web et citations courantes contrôlées avant persistance.
- [x] Domaine explicitement demandé, pertinence simple et associations
  équipe-score contrôlés génériquement ; URL officielle directe préservée.
- [x] Web désactivé : refus conversationnel persistant, sans réseau ni modèle.
- [x] Validation automatisée et parcours Internet réel isolé réussis ; aucune
  modification du superviseur pour l’incident `stdin.empty` non reproductible.
- [x] Première campagne manuelle de l’étape 16 réalisée dans Microsoft Edge ;
  les correctifs ultérieurs restent soumis à la revalidation finale ci-dessous.
- [x] Phase 16.3 — recours Edge à la demande pour les coquilles JavaScript,
  profil éphémère, proxy DNS épinglé limité à l’hôte initial et zéro clic.
- [x] Pagination sûre par liens directs, tableaux et `<details>` lus sans action,
  formulaires, comptes, transactions, téléchargements et réseau local refusés.
- [x] Tests Edge locaux isolés, site dynamique public réel, fermeture/annulation,
  non-régression 16.1/16.2 et preuves dans `docs/ETAPE_16_3_VALIDATION.md`.
- [x] Stabilisation finale : contrat de fiabilité 2.1 partagé par les trois
  profils, français permanent et messages déterministes à la première personne.
- [x] Case Web ponctuelle et booléen d’envoi supprimés ; autorisation uniquement
  textuelle ou issue d’une confirmation exacte, sous préférence globale active.
- [x] Messages longs acceptés, requêtes fournisseur toujours bornées ; lecture
  documentaire distinguée de la corroboration indépendante.
- [x] HTML volumineux lu partiellement sous la borne existante, extraits ciblés,
  provenance exacte de chaque page dynamique et validations de citations durcies.
- [x] Préparation de clôture : consultation directe officielle et document unique
  vérifiés avec le modèle réel ; refus prudent conservé si la sortie manque de citations.
- [x] Revalidation manuelle finale et commit utilisateur, confirmés par le prompt 17.

## ÉTAPE 17 — Markdown et interface — validation manuelle requise

- [x] Messages d'avertissement et d'erreur simplifiés en une phrase courte sans
  point-virgule, sans modifier les diagnostics ni les décisions de sécurité.
  Cycle Frontend corrigé : `node` vérifié reste l'autorité et l'ancien bootstrap
  `npm.cmd` ambigu ne bloque plus le démarrage ou l'arrêt. Validation : 388 tests
  backend, 71 frontend, 31 groupes Edge et cycle réel complet réussis.
- [x] Ajustements du 4 novembre : Projet compact, bouton principal voix/envoi/arrêt,
  interruption réelle du modèle et continuation après arrêt ; accueil spécialisé
  Programmation/Vétérinaire, historique agentique verrouillé hors profil chargé
  avec renommage/suppression disponibles, alertes de ressources centrées en haut.
  Validation : 388 tests backend, 64 frontend et 30 groupes Edge ; arrêt réel
  Général et réponse suivante vérifiés, puis Programmation rétabli.
- [x] Diagnostic modèle → SQLite → JSON → React ; contenu brut conservé.
- [x] CommonMark/GFM, tableaux défilants, code et copie indépendante des blocs.
- [x] HTML brut inerte, URL filtrées, images sans chargement, provenance des sources conservée.
- [x] Barre latérale, recherche, accueil, conversation centrale et saisie ajustable.
- [x] Ajustements demandés après essai : crayon/poubelle au survol, commandes
  vocales et envoi par icônes dans la saisie, Entrée/Maj+Entrée et marque simplifiée.
- [x] Saisie et commandes sur une ligne, quatre lignes maximum, champ vidé pendant
  l’envoi, profil à droite, menu contrasté et retrait de Régénérer.
- [x] Barre permanente, paramètres en haut, Démarrer/Arrêter en bas, libellé
  Conversations, « + » sans action et logo PNG fourni stocké dans le projet.
- [x] Derniers ajustements : titres latéraux agrandis, accueil limité au titre
  demandé, doublon Léa retiré, espacements égaux, infobulles Dictée/Envoyer et
  nouveau logo avec palette commune aux deux thèmes, contrastes vérifiés.
- [x] Accueil centré avec six titres aléatoires, renouvelés seulement à la
  navigation ; rail de saisie très fin après les commandes quand il faut défiler.
- [x] Commande principale voix/envoi selon le contenu du champ ; dictée séparée.
  Bouton éphémère en haut à gauche du chat, même taille que Paramètres.
- [x] Titre et actions de conversation limités à la barre latérale, bulle dédiée
  aux réponses de Léa, défilement Paramètres au bord droit et diagramme borné au
  chat ; son message d’indisponibilité est centré avec les mesures.
- [x] Séparateur supérieur et séparateurs inférieurs alignés jusqu’aux bords ;
  état normal du cœur retiré du pied de page, erreurs centrées en haut.
  Résultat des tâches Programmation réaffiché indépendamment du diff et des
  décisions de checkpoint, avec motif explicite en cas d’échec sans réponse.
- [x] Paramètres simplifiés en grille responsive ; carte Programmation retirée
  de cette page sans supprimer le profil ni ses contrôles métier. Microphone et
  voix locale réorganisés, validation centrée sans encadré ; le bouton Paramètres
  ouvre et ferme la page avec protection du brouillon.
- [x] Programmation utilise uniquement la saisie inférieure comme consigne
  OpenHands ; aucun chat Web parallèle, y compris si le texte mentionne Internet.
  Envoyer démarre directement le run, sans titre d’accueil ni bouton de départ
  supplémentaire. Annuler la tâche reste dans Projet et les décisions
  Accept/Rollback restent explicites sans résumé technique redondant.
- [x] Consignes texte enregistrées via le contrat de conversation existant,
  bulles pendant et après le run, Projet fixe au-dessus des messages et décisions
  de checkpoint dans la réponse. Révision relue après annulation.
  Deux runs réels vérifiés le 3 novembre : modification/test/rollback exact,
  puis lecture de fichier/acceptation ; aucun conteneur de ces essais conservé.
- [x] Frontend rangé par responsabilité dans `components/`, `hooks/`, `lib/` et
  `styles/`, sans déplacement du backend, des données, des modèles ni des contrats.
- [x] Complément explicitement demandé : chat éphémère Général en RAM, sans
  souvenirs ni historique persistant, Web manuel contrôlé sans navigateur sur disque.
  Fermeture, annulation, redémarrage, absence d’écriture SQLite et inférence réelle vérifiés.
- [x] Thèmes clair/sombre, réglage immédiat mémorisé localement dans l’interface.
- [x] Profils, Low/High existants, Web manuel, voix, ressources et OpenHands préservés.
- [x] Clavier, focus, navigation compacte permanente, réduction des mouvements et six tailles vérifiés dans Edge automatisé.
- [x] Tests frontend, non-régression backend complète, build et rapport `docs/ETAPE_17_VALIDATION.md`.
- [ ] Validation manuelle utilisateur de l’apparence et des flux réels dans Edge.

## Suite — non commencée

Le prompt 17 remplace l’ancien ordre pour le Markdown et la refonte visuelle.
La prochaine étape est le packaging Windows, sur nouvelle autorisation.
La génération d’images reste reportée. Les autres objectifs historiques restent
à réexaminer avant toute implémentation :

- Étape 19 — Speech-to-Speech.
- Étape 21 — Mémoire avancée.
- Étape 22 — Fine-tuning optionnel.
- Étape 23 — Sécurité finale.
- Étape 24 — Tests finaux.
- Étape 25 — Logiciel desktop final.

La vision en entrée est suspendue et reportée. Le profil Auxiliaire est supprimé
définitivement. Aucune de ces étapes suivantes n'est commencée.
