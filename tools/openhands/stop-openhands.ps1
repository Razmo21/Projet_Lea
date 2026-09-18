[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Aucune identité Canvas historique n'est adoptée ou arrêtée automatiquement.
Write-Host 'Aucune action : Agent Canvas est retiré du chemin Léa. Utilisez stop-openhands-sdk.ps1 seulement pour une instance SDK prouvée.'
