import assert from 'node:assert/strict'
import test from 'node:test'
import { ApiError } from '../../src/lib/api'
import { shortNotice } from '../../src/lib/notices'

test('Les alertes gardent leur gravité et les refus leur motif en quelques mots', () => {
  const examples = [
    ['RAM disponible critique.', 'RAM disponible critique'],
    ['Marge VRAM faible persistante.', 'VRAM disponible faible'],
    ['Docker est indisponible ; ouvre Docker Desktop manuellement.', 'Ouvrez Docker Desktop'],
    ['Le modèle actif ne répond pas ; son état est incertain.', 'Le modèle ne répond pas'],
    ['Le projet a changé après le run ; rollback refusé pour éviter un écrasement.', 'Restauration refusée car le projet a changé'],
    ['Arrêt non confirmé. Vérifie Docker puis redémarre Léa pour récupérer ce run.', 'Arrêt non confirmé à vérifier dans Docker'],
    ['Run terminé sans validation réelle : les changements ne peuvent pas être acceptés.', 'Changements non validés et non acceptables'],
    ['L’autorisation Web est absente, expirée ou déjà utilisée. Confirme la demande à nouveau.', 'Autorisez une nouvelle recherche Web'],
  ]
  for (const [message, expected] of examples) {
    assert.equal(shortNotice(message), expected)
    assert.ok(expected.length <= 80)
    assert.doesNotMatch(expected, /[;\r\n]/)
  }
})

test('Recherche, génération, contexte et réponse incomplète restent distincts', () => {
  const examples = [
    ['Recherche Web indisponible.', 'Recherche Web indisponible'],
    ['Des sources Web ont été collectées, mais le modèle local de Léa n’a pas produit de synthèse exploitable.', 'Synthèse Web impossible'],
    ['Le contexte transmis au modèle local dépasse sa fenêtre disponible.', 'Contexte trop long pour le modèle'],
    ['La réponse du modèle local a été tronquée.', 'Réponse incomplète'],
    ['Le modèle local de Léa n’a pas fourni de réponse exploitable.', 'Aucune réponse exploitable'],
    ['Le PDF ne contient aucun texte exploitable. Aucun OCR n’est exécuté.', 'Aucun texte lisible dans ce PDF'],
  ]
  for (const [message, expected] of examples) assert.equal(shortNotice(message), expected)
})

test('Les détails audio restent dans le diagnostic sans encombrer la notification', () => {
  const diagnostic = 'Ce navigateur ne peut pas décoder l’enregistrement, avant envoi à Whisper. '
    + 'audio/webm;codecs=opus, 30165 octets, 2092 ms'
  assert.equal(shortNotice(diagnostic, 'voice'), 'Essayez le microphone dans Microsoft Edge')
  assert.equal(shortNotice('Failed to fetch'), 'Connexion à Léa impossible')
  assert.equal(shortNotice('Microphone sélectionné absent. Vérifie les paramètres.', 'voice'), 'Microphone sélectionné absent')
})

test('Un diagnostic inconnu ne perd pas sa négation par troncature', () => {
  const diagnostic = 'La tâche semble terminée. Toutefois sa réussite ne peut pas être confirmée.'
  assert.equal(shortNotice(diagnostic, 'task'), 'Un problème affecte la tâche')
  assert.equal(shortNotice('Sauvegarde réussie ; cette affirmation est invalide', 'preferences'), 'Les paramètres ne sont pas confirmés')
  assert.equal(shortNotice('Erreur inconnue\n' + 'détail '.repeat(200)), 'Cette action est impossible')
  assert.equal(shortNotice(''), '')
  assert.equal(shortNotice(null), '')
  assert.equal(shortNotice('...'), 'Cette action est impossible')
  // Une clé héritée ne doit jamais devenir une valeur React non textuelle.
  for (const message of ['constructor', 'toString', '__proto__']) {
    assert.equal(shortNotice(message), message)
  }
})

test('La présentation ne modifie ni le statut API ni le diagnostic original', () => {
  const detail = 'Le projet a changé après le run ; rollback refusé pour éviter un écrasement.'
  const failure = new ApiError(409, detail)
  assert.equal(shortNotice(failure.message, 'task'), 'Restauration refusée car le projet a changé')
  assert.equal(failure.message, detail)
  assert.equal(failure.status, 409)
})
