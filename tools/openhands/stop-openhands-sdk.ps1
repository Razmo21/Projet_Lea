[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Arrete seulement le conteneur et le llama-server prouves par le state SDK local.
Import-Module -Force (Join-Path $PSScriptRoot 'OpenHands.Sdk.Common.psm1')

$state = Read-OpenHandsSdkState
if ($null -eq $state) {
    Write-Output 'Aucun etat SDK OpenHands local : aucun processus ni conteneur ne sera touche.'
    exit 0
}

try {
    Stop-OpenHandsSdkAgentServer -State $state
    Stop-OpenHandsSdkLlamaServer -State $state
    Set-OpenHandsSdkPhase -State $state -Phase 'stopped'
    Write-OpenHandsSdkStateAtomically -State $state
    Get-OpenHandsSdkStatus | ConvertTo-Json -Depth 20
} catch {
    Set-OpenHandsSdkPhase -State $state -Phase 'failed' -Failure $_.Exception.Message
    Write-OpenHandsSdkStateAtomically -State $state
    throw
}
