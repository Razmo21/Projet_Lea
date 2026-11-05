# PROJET LÉA — ÉTAPE 17
## Refonte Markdown et interface graphique complète — Léa v1.0

Tu dois réaliser l'intégralité de l'étape 17 du projet Léa, situé actuellement dans :

`L:\Projet_Lea`

L'étape 16 (Web Gateway) est terminée, validée manuellement et commitée.

**Objectif : transformer l'interface actuelle de Léa en une interface conversationnelle moderne, élégante, cohérente et ergonomique, fortement inspirée de ChatGPT, tout en conservant intégralement ses fonctionnalités existantes.**

Il s'agit de la dernière grande refonte visuelle avant le packaging de Léa en application Windows v1.0.

Cette étape comprend deux phases obligatoires, à réaliser dans cet ordre :

1. **Correction complète du rendu Markdown.**
2. **Refonte visuelle et ergonomique de l'interface.**

Tu dois réaliser les deux phases dans cette même intervention, puis exécuter les vérifications finales.

Aucune capture d'écran de référence ne sera fournie pour le moment. Utilise donc une direction artistique cohérente, inspirée des interfaces conversationnelles modernes, notamment ChatGPT, sans copier ses logos, ses marques ou ses composants propriétaires.

---

# 1. Analyse préalable obligatoire

Avant toute modification, lis et examine :

- `AGENTS.md`
- `README.md`
- `TODO.md`
- `CHANGELOG.md`
- `docs/DECISIONS.md`
- La documentation des étapes 14 à 16 pertinente pour les fonctionnalités visibles.
- Les composants React et TypeScript.
- Les feuilles CSS existantes.
- La structure des conversations et des messages.
- La gestion des profils.
- Les composants vocaux.
- L'interface du Web Gateway.
- Les composants propres à Programmation et OpenHands.
- Les paramètres et les états techniques.
- Les tests frontend existants.

Examine également le statut Git.

Ne pars pas du principe que les noms de fichiers, l'architecture ou les bibliothèques sont identiques à ceux d'une version antérieure. Travaille à partir de l'état réel du dépôt.

Identifie les éléments à conserver, les composants réutilisables et les parties qui nécessitent réellement une refonte.

**Ne réécris pas toute l'application pour améliorer son apparence.**

Évite également d'ajouter une nouvelle bibliothèque ou un framework uniquement pour gagner du temps si la solution existante peut être améliorée proprement.

---

# 2. Phase A — Correction complète du Markdown

C'est la première priorité de l'étape.

Depuis les premières versions de Léa, certaines réponses présentent des problèmes d'affichage :

- `\*\*texte\*\*` au lieu du gras ;
- des titres Markdown visibles sous forme de caractères bruts ;
- des caractères d'échappement supplémentaires ;
- des entités comme `&#x20;` ;
- des listes mal rendues ;
- des blocs de code insuffisamment formatés ;
- des réponses Web affichant du Markdown littéral.

Ces anomalies existent depuis longtemps et doivent être corrigées à leur source.

## 2.1. Diagnostic

Retrace le parcours complet du texte :

**Modèle → backend → validation éventuelle → SQLite → API → frontend → rendu → copie.**

Détermine précisément où se produisent les échappements inutiles et les transformations incorrectes.

Distingue :

- le Markdown réellement produit par le modèle ;
- le Markdown enregistré ;
- les caractères échappés volontairement ;
- les caractères échappés plusieurs fois ;
- les entités HTML ;
- le rendu React ;
- le contenu brut utilisé par les boutons Copier.

Ne traite pas ce problème avec une expression régulière globale qui retirerait simplement tous les antislashs.

Ne transforme pas non plus le contenu des blocs de code, les chemins Windows ou les caractères que l'utilisateur souhaite afficher littéralement.

## 2.2. Moteur de rendu Markdown

Privilégie une solution standard et maintenue, adaptée à React et TypeScript.

Évalue notamment :

- `react-markdown`
- `remark-gfm`
- `remark-math` et `rehype-katex` si nécessaires pour les expressions mathématiques
- `rehype-sanitize` si pertinent pour la configuration retenue

N'ajoute que les dépendances réellement nécessaires.

Le rendu doit prendre en charge correctement :

- Paragraphes et retours à la ligne.
- Gras, italique et texte barré.
- Titres de différents niveaux.
- Listes numérotées et non numérotées.
- Listes imbriquées.
- Cases à cocher Markdown.
- Citations.
- Liens.
- Tableaux GFM.
- Code en ligne.
- Blocs de code avec indication du langage.
- Séparateurs horizontaux.
- Expressions mathématiques courantes, si leur prise en charge est intégrée.
- Texte comportant des caractères français, accents et symboles Unicode.
- Markdown incomplet ou mal formé, sans provoquer de plantage.

Les tableaux larges doivent rester utilisables dans une fenêtre étroite.

Les blocs de code doivent disposer d'un bouton permettant de copier uniquement le code.

Si une coloration syntaxique est ajoutée, elle doit être légère et ne pas provoquer de ralentissements disproportionnés.

## 2.3. Sécurité du rendu

Les messages peuvent contenir du texte provenant du modèle, de l'utilisateur ou de sources Web.

Ils doivent tous être considérés comme potentiellement non fiables pour le rendu.

Interdictions :

- Exécuter du JavaScript contenu dans un message.
- Injecter directement du HTML non fiable.
- Utiliser `dangerouslySetInnerHTML` sur du contenu non assaini.
- Autoriser des URL dangereuses dans les liens.
- Interpréter une instruction présente dans une source Web comme une commande système.

Conserve les protections contre les injections et les faux liens.

Les références Web `[S1]`, `[S2]`, etc. doivent conserver leur provenance contrôlée par le backend. Ne transforme pas une citation inventée par le modèle en source valide.

## 2.4. Conservation des messages

Le rendu Markdown doit fonctionner correctement :

- Pendant la génération.
- À la fin de la génération.
- Après un changement de conversation.
- Après actualisation de la page.
- Après redémarrage de Léa.
- Lors de la consultation d'anciens messages SQLite.
- Dans les profils Général et Vétérinaire.
- Dans les zones textuelles du profil Programmation lorsque le Markdown y est applicable.

Évite les migrations destructrices des conversations existantes.

Ne modifie pas silencieusement les données historiques dans SQLite.

Le bouton Copier doit fournir un texte exploitable et fidèle, sans ajouter d'échappements ou d'entités artificiels.

## 2.5. Tests Markdown obligatoires

Ajoute des tests automatisés couvrant les principales syntaxes.

Inclure des exemples précis comme :

- `**bonjour**`
- `\*\*bonjour\*\*` lorsque les antislashs sont intentionnels ou proviennent d'une ancienne anomalie identifiée.
- `## Titre`
- Des tableaux avec plusieurs colonnes.
- Des blocs de code Python et TypeScript.
- Des commandes PowerShell comportant des chemins Windows.
- Des listes imbriquées.
- Des liens HTTPS.
- Des entités HTML.
- Des citations `[S1]`.
- Du contenu potentiellement malveillant.
- Des réponses enregistrées, puis rechargées.

Vérifie que la correction d'un cas ne détériore pas les autres.

**La phase A n'est terminée que lorsque le Markdown est correctement interprété et que les tests correspondants passent.**

---

# 3. Phase B — Refonte visuelle complète

Une fois le Markdown stabilisé, refais l'interface.

## 3.1. Direction artistique

Je veux une interface proche de l'expérience ChatGPT :

- Minimaliste.
- Moderne.
- Très lisible.
- Épurée.
- Élégante.
- Cohérente.
- Agréable pendant de longues conversations.
- Professionnelle, sans surcharge visuelle.

L'interface ne doit pas ressembler à un tableau de bord technique ou à un prototype de développement.

Utilise une hiérarchie visuelle claire, des espacements réguliers, des bordures discrètes et une typographie soignée.

Évite les effets décoratifs excessifs, les dégradés agressifs, les couleurs trop saturées et les animations inutiles.

Je préfère une interface très bien exécutée et simple plutôt qu'une interface spectaculaire mais incohérente.

## 3.2. Système de design

Crée un système visuel centralisé et maintenable comprenant :

- Variables de couleurs.
- Variables de thèmes.
- Typographie.
- Espacements.
- Rayons de bordure.
- Dimensions des panneaux.
- Comportements responsive.
- États de survol.
- États de sélection.
- États désactivés.
- Indicateurs de chargement.
- Animations discrètes.

Utilise des composants réutilisables plutôt que de répéter les mêmes styles dans plusieurs fichiers.

Évite les valeurs arbitraires et les exceptions CSS ajoutées les unes après les autres.

L'objectif est d'obtenir un code frontend lisible et facile à modifier pendant le développement de Léa v2.0.

## 3.3. Thème clair et thème sombre

Prévois deux thèmes cohérents :

**Thème clair :**
- Fond clair et reposant.
- Textes foncés très lisibles.
- Barre latérale légèrement différenciée.
- Bordures fines.
- Couleurs d'accent discrètes.

**Thème sombre :**
- Fond sombre neutre.
- Contrastes maîtrisés.
- Textes confortables à lire.
- Panneaux clairement différenciés.
- Aucun noir ou blanc extrême utilisé systématiquement sans raison.

Le changement de thème doit être fonctionnel et conserver une apparence cohérente dans toutes les sections.

Réutilise les mécanismes de paramètres existants si possible.

## 3.4. Organisation générale

Je veux retrouver les grands principes ergonomiques de ChatGPT.

### Barre latérale

- Présentation compacte.
- Liste des conversations.
- Nouvelle conversation facilement accessible.
- Recherche de conversations.
- Conversation sélectionnée clairement identifiable.
- Actions existantes de renommage, suppression et navigation conservées.
- Regroupement visuel pertinent, sans inventer des fonctionnalités inexistantes.
- Possibilité de réduire ou masquer la barre latérale.
- Adaptation aux fenêtres étroites.

### Zone principale

- Conversation au centre.
- Largeur de lecture confortable.
- Espacement régulier entre les messages.
- Typographie adaptée aux réponses courtes et longues.
- Titres, tableaux et blocs de code bien intégrés.
- Aucun débordement horizontal global.
- Défilement naturel.
- Apparence cohérente pour les messages utilisateur, les réponses de Léa et les erreurs.

Évite d'entourer chaque élément de grandes cartes inutiles.

Les messages doivent être facilement distinguables sans alourdir l'ensemble de l'interface.

### Zone de saisie

- Champ de saisie moderne, avec coins arrondis.
- Ajustement de la hauteur selon le contenu.
- Bouton d'envoi clairement identifiable.
- États d'attente et de génération visibles.
- Conservation du comportement clavier actuel, notamment l'envoi et les retours à la ligne.
- Conservation des commandes d'annulation et de régénération.
- Accès clair aux fonctions vocales existantes.

La zone de saisie doit rester confortable à utiliser lorsque la conversation devient longue.

### Écran d'accueil

Lorsqu'aucune conversation n'est sélectionnée, présenter une interface simple et accueillante.

Afficher Léa et une invitation naturelle à commencer une conversation.

Ne pas ajouter de suggestions fictives qui déclencheraient des fonctions inexistantes.

---

# 4. Préserver les particularités de Léa

La refonte ne doit pas transformer Léa en copie fonctionnelle de ChatGPT.

Elle doit conserver ses propres capacités et ses propres flux.

## 4.1. Profils

Préserver :

- Général.
- Vétérinaire.
- Programmation.

Le changement de profil doit être simple, clairement visible et cohérent avec l'interface.

Conserver les paramètres Low/High uniquement là où ils existent réellement.

**Programmation n'est pas un profil de discussion conventionnelle.**

Il repose sur la sélection d'un workspace et sur OpenHands. Ne lui ajouter ni un faux chat conventionnel ni un sélecteur Low/High.

## 4.2. Web Gateway

Préserver :

- Le verrou Web global dans les paramètres.
- La recherche uniquement sur autorisation explicite.
- Les demandes de confirmation.
- Les sources contrôlées par le backend.
- Les messages d'erreur.
- La lecture documentaire.
- L'historique des sources.

Ne réintroduis pas l'ancien bouton « Utiliser le Web uniquement pour cette question ».

Les panneaux de sources doivent être lisibles et visuellement intégrés à la conversation, sans perdre les informations utiles.

## 4.3. Voix

Conserver les deux modes existants :

- Dictée.
- Conversation vocale.

La dictée doit rester modifiable avant envoi.

Le mode de conversation vocale doit conserver son fonctionnement actuel, sans imposer l'affichage permanent de transcriptions.

Améliorer uniquement leur présentation, les états visuels et l'ergonomie, sans réécrire le traitement audio.

Préserver le STT local et la voix Estelle.

Ne commence pas le chantier Speech-to-Speech avancé.

## 4.4. Programmation et OpenHands

Conserver toutes les fonctions existantes :

- Sélection d'un workspace autorisé.
- Envoi d'une tâche.
- Statuts d'exécution.
- Résultats.
- Annulation.
- Checkpoints.
- Acceptation ou rollback.
- Contrôles de Docker existants.

Moderniser la présentation de ces éléments sans modifier leur logique métier.

Ne démarre pas Docker automatiquement si ce comportement n'est pas déjà autorisé par les paramètres.

## 4.5. Centre de paramètres

Rendre les paramètres :

- Faciles à trouver.
- Bien organisés.
- Cohérents entre les profils.
- Lisibles.
- Fonctionnels.
- Agréables à utiliser.

Conserver tous les réglages existants.

Ne pas ajouter de fonctions factices simplement pour ressembler à ChatGPT.

## 4.6. Statuts techniques

Les états du modèle, du backend, de Docker et des autres composants doivent rester disponibles lorsque nécessaire, mais ne doivent pas dominer l'interface.

Regrouper les informations techniques dans des zones discrètes et compréhensibles.

Les erreurs doivent rester visibles, précises et exploitables.

---

# 5. Adaptation et accessibilité

La future v1.0 sera transformée en application Windows. L'interface doit donc fonctionner correctement dans une fenêtre redimensionnable.

Tester plusieurs tailles :

- Grande fenêtre de bureau.
- Fenêtre de bureau moyenne.
- Fenêtre étroite.
- Taille minimale raisonnable.
- Format mobile étroit à titre de vérification responsive.

Exigences :

- Aucun bouton essentiel inaccessible.
- Aucune fenêtre modale coupée.
- Aucun tableau provoquant un débordement global.
- Aucun panneau masquant définitivement les autres commandes.
- Contraste suffisant.
- Navigation au clavier.
- Focus visible.
- Boutons avec intitulés accessibles.
- États de chargement compréhensibles.
- Respect des préférences de réduction des animations.

Éviter les animations coûteuses, les effets graphiques lourds et les composants inutiles.

Le PC actuel dispose de ressources limitées et l'interface doit rester fluide même lorsque le modèle local travaille.

---

# 6. Préparer la future application Windows

Cette étape ne doit pas encore créer l'application Windows.

Cependant, l'interface doit être compatible avec ce futur packaging.

En particulier :

- Ne pas supposer qu'elle sera toujours ouverte dans un onglet Edge.
- Éviter les chemins absolus propres à un seul PC.
- Ne pas lier les composants visuels à `L:\Projet_Lea`.
- Conserver les échanges frontend/backend existants.
- Éviter d'introduire des dépendances réseau externes pour afficher les composants.
- Ne pas charger de ressources graphiques ou de polices depuis un CDN au fonctionnement normal.
- Préserver le fonctionnement entièrement local.

Le projet sera transféré sur un nouveau SSD interne lors du passage à Léa v2.0.

Les souvenirs personnels et paramètres utilisateur pourront être réinitialisés lors de cette migration, mais le code source et les configurations techniques nécessaires devront rester transportables.

Ne réalise pas encore cette migration.

---

# 7. Qualité du code

Je veux une refonte propre, pas un empilement de correctifs CSS.

Exigences :

- Composants React clairement séparés.
- CSS organisé logiquement.
- Variables de design centralisées.
- Suppression des styles devenus inutiles.
- Pas de duplication massive.
- Pas de code mort.
- Pas de commentaires répétant inutilement le code.
- Commentaires utiles pour les décisions non évidentes.
- TypeScript correctement typé.
- Gestion correcte des états et des effets.
- Gestion des ressources et des événements à la fermeture des composants.
- Pas de dépendances superflues.
- Pas de régression dans les flux fonctionnels.

Tu peux réorganiser les composants frontend si cela améliore réellement leur maintenabilité.

Évite en revanche une refonte du backend, de SQLite ou des autres sous-systèmes sans nécessité démontrée.

Ne modifie pas les contrats de fiabilité, les permissions ou la logique des modèles.

---

# 8. Tests automatisés obligatoires

Ajoute ou adapte les tests frontend pour vérifier :

1. Rendu correct du Markdown.
2. Absence de double échappement.
3. Gestion sûre du contenu HTML et des liens.
4. Affichage des sources Web.
5. Persistance de l'affichage après rechargement.
6. Changement de thème.
7. Ouverture et fermeture de la barre latérale.
8. Sélection et changement de conversation.
9. Sélection des profils.
10. Affichage des paramètres.
11. Envoi de message.
12. Annulation et régénération.
13. Fonctionnement des commandes vocales visibles.
14. Affichage des états OpenHands.
15. Affichage des erreurs.
16. Absence de débordements majeurs aux dimensions testées.

Exécute :

- Les tests frontend.
- Le build TypeScript/Vite.
- Les contrôles statiques disponibles.
- Les tests backend pertinents si tu modifies une interface contractuelle partagée.

Si un navigateur local automatisé est disponible, utilise-le pour vérifier le rendu réel et les interactions.

Tu peux utiliser les outils de navigateur déjà présents dans le projet.

**N'impose pas l'installation de nouveaux serveurs MCP ou de plugins externes pour terminer cette étape.**

Lorsque tu ne peux pas vérifier visuellement un résultat, indique-le honnêtement dans le rapport.

---

# 9. Documentation

Actualise les documents existants concernés :

- `README.md`
- `TODO.md`
- `CHANGELOG.md`
- `docs/DECISIONS.md`, si une décision d'architecture importante est prise.

Documente brièvement :

- Le nouveau système de rendu Markdown.
- Les principaux composants visuels.
- Le fonctionnement des thèmes.
- Les dépendances ajoutées.
- Les choix importants de sécurité et d'accessibilité.
- Les limites éventuelles restantes.

L'étape 17 doit être clairement distinguée de l'étape suivante, consacrée au packaging Windows.

---

# 10. Critères de réussite

Je considérerai cette étape comme techniquement terminée lorsque :

- Le Markdown est correctement affiché.
- Les caractères d'échappement parasites sont corrigés sans altérer les contenus littéraux légitimes.
- Les tableaux, listes, blocs de code et liens sont correctement présentés.
- L'interface possède une apparence moderne, cohérente et proche de l'expérience ChatGPT.
- Les thèmes clair et sombre fonctionnent.
- La barre latérale et la zone conversationnelle sont ergonomiques.
- Les fonctionnalités existantes sont conservées.
- L'interface reste utilisable dans une fenêtre redimensionnée.
- Le code est propre et maintenable.
- Les tests automatisés réussissent.
- Le projet compile sans erreur.

Les tests automatisés ne remplacent pas ma validation manuelle.

---

# 11. Rapport final obligatoire

À la fin de ton intervention, fournis :

1. Un résumé de la correction Markdown, avec les causes identifiées.
2. Un résumé de la nouvelle interface et de ses principaux composants.
3. La liste des fichiers modifiés ou ajoutés.
4. Les dépendances ajoutées et leurs justifications.
5. Les tests exécutés et leurs résultats exacts.
6. Les vérifications visuelles effectuées.
7. Les limitations restantes.
8. Les tests manuels que je dois effectuer dans Edge.
9. Les éventuels points à préparer pour le packaging Windows.

Effectue le travail complet sans t'arrêter entre les phases A et B, sauf obstacle technique réellement bloquant.

Ne fais aucun commit ni push.

Ne commence pas l'étape suivante.

**Priorité : une interface élégante, très lisible et maintenable, avec un Markdown fiable et aucune régression fonctionnelle.**

Léa v1.0 doit enfin avoir l'apparence d'une véritable application d'intelligence artificielle personnelle.