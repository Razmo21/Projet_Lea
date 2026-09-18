[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Le chemin Canvas historique est volontairement retiré : il ne doit jamais
# redevenir une dépendance cachée du profil Programmation final.
throw 'Agent Canvas est retiré du chemin de fonctionnement Léa. Utilisez start-openhands-sdk.ps1 (Agent Server / SDK minimal).'
