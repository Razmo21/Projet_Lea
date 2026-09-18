[CmdletBinding()]
param(
    [int]$ContextSize = 22000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Charge le contrat SDK independant afin de ne jamais demarrer Canvas depuis cette commande.
Import-Module -Force (Join-Path $PSScriptRoot 'OpenHands.Sdk.Common.psm1')

$config = Get-OpenHandsSdkConfig
Assert-OpenHandsSdkConfiguredContext -ContextSize $ContextSize | Out-Null
$state = Read-OpenHandsSdkState
if ($null -eq $state) {
    $state = New-OpenHandsSdkState -ContextSize $ContextSize
} elseif ([string](Get-OpenHandsSdkObjectValue -Object $state -Name 'phase') -in @('starting', 'model_ready', 'agent_ready', 'running')) {
    # Refuse une seconde allocation lorsque l'etat correspond encore a une instance reellement active.
    $currentStatus = Get-OpenHandsSdkStatus
    $agentRunning = $null -ne $currentStatus.agent_server -and [bool]$currentStatus.agent_server.Running
    $modelRunning = $null -ne $currentStatus.model -and [bool]$currentStatus.model.Exists
    if ($agentRunning -or $modelRunning) {
        throw 'Une instance SDK existante est encore active ; refuse le double demarrage.'
    }
    Set-OpenHandsSdkPhase -State $state -Phase 'stopped'
    Write-OpenHandsSdkStateAtomically -State $state
}

# Verifie les prerequis lourds une seule fois avant d'allouer RAM, GPU ou conteneur.
Assert-OpenHandsSdkDockerReady | Out-Null
Assert-OpenHandsSdkModelAndRuntime | Out-Null
Assert-OpenHandsSdkWorkspaceRoot | Out-Null
Set-OpenHandsSdkObjectValue -Object $state -Name 'selected_context' -Value $ContextSize
Set-OpenHandsSdkPhase -State $state -Phase 'starting'
Write-OpenHandsSdkStateAtomically -State $state

try {
    Start-OpenHandsSdkLlamaServer -State $state -ContextSize $ContextSize | Out-Null
    $model = Get-OpenHandsSdkObjectValue -Object $state -Name 'model'
    $samples = Get-OpenHandsSdkStableResourceSamples -ModelRecord (Get-OpenHandsSdkObjectValue -Object $model -Name 'listener')
    $barrier = Test-OpenHandsSdkMemoryBarrier -Samples $samples
    if (-not $barrier.Passed) {
        throw "La marge RAM a $ContextSize tokens est critique sous 4 Gio : $([math]::Round($barrier.MinimumAvailableRamBytes / 1GB, 2)) Gio."
    }
    Start-OpenHandsSdkAgentServer -State $state -ContextSize $ContextSize | Out-Null
    Set-OpenHandsSdkPhase -State $state -Phase 'agent_ready'
    Write-OpenHandsSdkStateAtomically -State $state
    [pscustomobject]@{
        agent_server_url = "http://$($config.AgentHost):$($config.AgentHostPort)"
        model_url = "http://$($config.LlamaHost):$($config.LlamaPort)/v1/models"
        model_alias = $config.ModelAlias
        context_size = $ContextSize
        workspace = $config.WorkspaceRoot
        memory_classification = $barrier.Classification
        minimum_available_ram_gib = [math]::Round($barrier.MinimumAvailableRamBytes / 1GB, 3)
        note = 'Agent Server minimal actif ; Agent Canvas n est pas demarre par cette commande.'
    } | ConvertTo-Json -Depth 6
} catch {
    try { Stop-OpenHandsSdkAgentServer -State $state } catch { Write-Warning $_.Exception.Message }
    try { Stop-OpenHandsSdkLlamaServer -State $state } catch { Write-Warning $_.Exception.Message }
    Set-OpenHandsSdkPhase -State $state -Phase 'failed' -Failure $_.Exception.Message
    Write-OpenHandsSdkStateAtomically -State $state
    throw
}
