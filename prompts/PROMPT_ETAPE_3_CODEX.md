# Prompt — Étape 3 du Projet Léa

Lis intégralement les fichiers suivants avant toute modification :

- `AGENTS.md`
- `README.md`
- `TODO.md`
- `docs/DECISIONS.md`
- `prompts/PROMPT_ETAPE_1_CODEX.md`
- `prompts/PROMPT_ETAPE_2_CODEX.md`

Nous commençons uniquement l’étape 3 du Projet Léa.

# Objectif

Relier le frontend React existant au backend FastAPI existant.

Le but est que la question saisie dans la page localhost soit envoyée au backend via :

`POST /test-response`

puis que la réponse fictive renvoyée par FastAPI soit affichée dans l’interface.

Aucun modèle d’IA ne doit être utilisé.

---

# Comportement attendu

Quand l’utilisateur écrit par exemple :

`allo ?`

puis clique sur :

`Envoyer`

le fonctionnement doit être :

```text
Frontend React
    ↓
POST /test-response
    ↓
Backend FastAPI
    ↓
Réponse JSON
    ↓
Frontend React
    ↓
Affichage de la réponse
```

Le backend doit renvoyer :

```json
{
  "answer": "Léa n'est pas encore connectée à son modèle."
}
```

Le frontend doit afficher cette valeur reçue du backend.

La réponse ne doit donc plus être générée directement dans le frontend.

---

# Contraintes

Le frontend actuel fonctionne déjà et doit rester simple.

Ne refais pas l’interface.

Ne modifie le CSS que si une petite adaptation est réellement nécessaire au fonctionnement.

Le backend existant doit rester minimal.

---

# Communication frontend / backend

Le frontend tourne normalement sur :

`http://127.0.0.1:5173`

ou :

`http://localhost:5173`

Le backend tourne sur :

`http://127.0.0.1:8000`

Configure uniquement ce qui est nécessaire pour permettre cette communication locale.

Si CORS est nécessaire, autorise uniquement les origines locales utiles au développement :

- `http://127.0.0.1:5173`
- `http://localhost:5173`

N’utilise pas `*` si cela n’est pas nécessaire.

---

# Gestion minimale des erreurs

Ajoute seulement une gestion d’erreur simple.

Si le backend est arrêté ou inaccessible, affiche un message clair dans la zone de réponse, par exemple :

`Impossible de contacter le backend de Léa.`

Ne crée pas de système complexe de gestion d’erreurs.

---

# Avant de coder

Explique brièvement :

1. ce que tu vas modifier ;
2. quels fichiers seront concernés ;
3. comment le frontend communiquera avec FastAPI ;
4. si une configuration CORS est nécessaire ;
5. les commandes que tu comptes utiliser.

Puis réalise uniquement cette étape.

---

# Vérifications obligatoires

Après modification :

1. démarre le backend FastAPI ;
2. démarre le frontend Vite ;
3. vérifie que les deux démarrent sans erreur ;
4. ouvre la page locale ;
5. envoie une question de test ;
6. confirme que le frontend reçoit réellement la réponse de `POST /test-response` ;
7. vérifie que la réponse affichée est :

`Léa n'est pas encore connectée à son modèle.`

8. vérifie le comportement lorsque le backend est indisponible ;
9. liste les fichiers créés ou modifiés ;
10. liste les commandes utilisées ;
11. signale toute erreur ou avertissement restant ;
12. arrête les serveurs de test si nécessaire ;
13. arrête-toi et attends la validation de l’utilisateur.

---

# Interdictions absolues

Ne fais PAS :

- de modèle d’IA ;
- de llama.cpp ;
- de téléchargement de modèle ;
- de mémoire ;
- de SQLite ;
- de base de données ;
- de RAG ;
- d’accès à `IA_WORKSPACE` ;
- d’accès Internet ;
- de système de profils ;
- de Tauri ;
- de Docker ;
- d’authentification ;
- de télémétrie ;
- de streaming de tokens ;
- de système de conversations ;
- de sauvegarde de messages ;
- de fonctionnalité future.

N’entame pas l’étape 4.

---

# Critères de validation

L’étape 3 est terminée uniquement si :

- le frontend démarre correctement ;
- le backend démarre correctement ;
- le bouton `Envoyer` transmet réellement la question à FastAPI ;
- FastAPI répond via `/test-response` ;
- le frontend affiche la réponse reçue du backend ;
- un message simple apparaît si le backend est inaccessible ;
- aucune fonctionnalité supplémentaire n’a été ajoutée.

Une fois ces critères atteints, arrête-toi.
