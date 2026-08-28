[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Affiche des donnees de statut sans adopter, arreter ou modifier un composant existant.
Import-Module -Force (Join-Path $PSScriptRoot 'OpenHands.Sdk.Common.psm1')

Get-OpenHandsSdkStatus | ConvertTo-Json -Depth 20
