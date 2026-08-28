[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Importe l'outillage isolé : ce script ne démarre ni lea.ps1, ni FastAPI, ni Vite.
Import-Module (Join-Path $PSScriptRoot 'OpenHands.Common.psm1') -Force -DisableNameChecking

$state = $null
$attemptOwnsRuntime = $false
try {
    # Valide d'abord le moteur local et le seul workspace permis, puis refuse rapidement tout double démarrage.
    Assert-OpenHandsDockerReady
    $workspace = Assert-OpenHandsWorkspaceRoot

    $state = Read-OpenHandsState
    if ($null -ne $state -and ([string]$state.phase -eq 'starting' -or [string]$state.phase -eq 'failed')) {
        throw "L’état OpenHands est $($state.phase) ; exécutez status-openhands.ps1 puis stop-openhands.ps1 avant une nouvelle tentative."
    }

    # Refuse les doubles démarrages et tout écart d'identité avant de vérifier les ports libres.
    $current = Get-OpenHandsStatus
    if ($null -ne $current.container -and $current.container.Exists) {
        if (-not $current.container.Verified) {
            throw "Le conteneur enregistré est ambigu : $($current.container.Reason)"
        }

        if ($current.container.Running) {
            throw 'Double démarrage OpenHands refusé : le conteneur géré est déjà actif.'
        }
    }

    if (($null -ne $current.model_launcher -and $current.model_launcher.Exists) -or ($null -ne $current.model_listener -and $current.model_listener.Exists)) {
        throw 'Double démarrage OpenHands refusé : un llama-server enregistré est encore actif.'
    }

    # Le contrôle coûteux du GGUF et de l'image n'est fait qu'après le refus d'un second lancement actif.
    $runtime = Assert-OpenHandsModelAndRuntime
    [void](Ensure-OpenHandsImage)
    if ($null -eq $state) {
        $state = New-OpenHandsState
        Write-OpenHandsStateAtomically -State $state
    }

    $config = Get-OpenHandsConfig
    Assert-OpenHandsPortFree -Port $config.LlamaPort -Label 'llama-server OpenHands'
    Assert-OpenHandsPortFree -Port $config.HostPort -Label 'Agent Canvas OpenHands'
    Set-OpenHandsPhase -State $state -Phase 'starting'
    Write-OpenHandsStateAtomically -State $state

    # Lance d'abord l'API LLM dédiée, mesure sa mémoire, puis seulement le conteneur sandboxé.
    $attemptOwnsRuntime = $true
    $state = Start-OpenHandsLlamaServer -State $state
    [void](Start-OpenHandsManagedContainer -State $state)
    $uiUrl = Wait-ForOpenHandsUi -TimeoutSeconds 180
    if (-not (Test-OpenHandsWindowsLlamaEndpoint)) {
        throw 'Le endpoint /v1/models Windows ne répond plus après le lancement du conteneur.'
    }

    [void](Test-OpenHandsContainerLlamaEndpoint -State $state)
    Set-OpenHandsPhase -State $state -Phase 'running'
    Write-OpenHandsStateAtomically -State $state

    Write-Host 'OpenHands local est démarré.'
    Write-Host "URL : $uiUrl"
    Write-Host "Workspace monté : $workspace -> $($config.WorkspaceContainerPath)"
    Write-Host "LLM : openai/$($config.ModelAlias) via http://host.docker.internal:$($config.LlamaPort)/v1"
    Write-Host "Modèle vérifié : $($runtime.Sha256)"
} catch {
    $failure = $_.Exception.Message
    if ($attemptOwnsRuntime -and $null -ne $state) {
        # Ne nettoie que l'instance dont l'état et les identités restent vérifiables ; sinon conserve les preuves pour diagnostic.
        try {
            [void](Stop-OpenHandsManagedInstance -State $state)
        } catch {
            Write-Warning "Nettoyage limité : $($_.Exception.Message)"
        }

        Set-OpenHandsPhase -State $state -Phase 'failed' -Failure $failure
        Write-OpenHandsStateAtomically -State $state
    }

    throw
}
