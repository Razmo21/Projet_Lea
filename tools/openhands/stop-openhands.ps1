[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Arrête seulement les objets dont l'état persistant et les empreintes prouvent la propriété du bootstrap.
Import-Module (Join-Path $PSScriptRoot 'OpenHands.Common.psm1') -Force -DisableNameChecking
$state = Read-OpenHandsState

if ($null -eq $state) {
    Write-Host 'Aucun état OpenHands enregistré : aucun conteneur ni processus ne sera arrêté.'
    return
}

[void](Stop-OpenHandsManagedInstance -State $state)
Write-Host 'OpenHands et son llama-server gérés sont arrêtés ; le volume lea_openhands_state est conservé.'
