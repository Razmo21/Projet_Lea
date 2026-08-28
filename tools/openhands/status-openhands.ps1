[CmdletBinding()]
param([switch]$Json)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Lit les identités et ressources sans démarrer, arrêter ou adopter de processus.
Import-Module (Join-Path $PSScriptRoot 'OpenHands.Common.psm1') -Force -DisableNameChecking
$status = Get-OpenHandsStatus

if ($Json) {
    $status | ConvertTo-Json -Depth 12
    return
}

$phase = if ($null -eq $status.state) { 'aucun état enregistré' } else { [string]$status.state.phase }
$image = if ($null -eq $status.state) { 'inconnue' } else { [string]$status.state.container.image }
$containerState = if ($null -eq $status.container) { 'inconnu' } elseif (-not $status.container.exists) { 'absent' } elseif (-not $status.container.verified) { "ambigu ($($status.container.reason))" } elseif ($status.container.running) { 'actif et vérifié' } else { 'arrêté et vérifié' }
$launcherState = if ($null -eq $status.model_launcher) { 'inconnu' } elseif (-not $status.model_launcher.exists) { 'absent' } elseif (-not $status.model_launcher.verified) { "ambigu ($($status.model_launcher.reason))" } else { "actif et vérifié (PID $($status.model_launcher.pid))" }
$listenerState = if ($null -eq $status.model_listener) { 'inconnu' } elseif (-not $status.model_listener.exists) { 'absent' } elseif (-not $status.model_listener.verified) { "ambigu ($($status.model_listener.reason))" } elseif ($status.model_listener.listening) { "écouteur vérifié (PID $($status.model_listener.pid))" } else { 'actif mais sans écoute confirmée' }

Write-Host "État OpenHands : $phase"
Write-Host "Docker : $(if ($status.docker_ready) { 'prêt' } else { "indisponible ($($status.docker_error))" })"
Write-Host "Conteneur : $containerState"
Write-Host "Image : $image"
Write-Host "UI : $($status.ui_url)"
Write-Host "LLM : $($status.model_url)"
Write-Host "Llama launcher : $launcherState"
Write-Host "Llama listener : $listenerState"
Write-Host "Workspace : $($status.workspace) -> /projects"

if ($null -ne $status.resources) {
    $availableGiB = [math]::Round(([int64]$status.resources.system_available_ram_bytes / 1GB), 2)
    Write-Host "RAM système disponible : $availableGiB Gio"
    if ($null -ne $status.resources.model) {
        $workingSetGiB = [math]::Round(([int64]$status.resources.model.working_set_bytes / 1GB), 2)
        $privateGiB = [math]::Round(([int64]$status.resources.model.private_bytes / 1GB), 2)
        Write-Host "RAM llama-server : WS $workingSetGiB Gio ; privée $privateGiB Gio"
    }

    if ($null -ne $status.resources.gpu_csv) {
        Write-Host "GPU (total, utilisée, libre, utilisation, température) : $($status.resources.gpu_csv -join ' | ')"
    } else {
        Write-Host 'GPU : mesure nvidia-smi indisponible.'
    }
}
