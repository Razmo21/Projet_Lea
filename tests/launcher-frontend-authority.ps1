# Vérifie la propriété Frontend sans lancer npm, Vite ni aucun processus réel.
$ErrorActionPreference = 'Stop'
$launcherPath = Join-Path $PSScriptRoot '..\lea.ps1'
$parseErrors = $null
$tokens = $null
$tree = [System.Management.Automation.Language.Parser]::ParseFile(
    $launcherPath, [ref]$tokens, [ref]$parseErrors
)
if ($parseErrors) { throw 'Syntaxe du lanceur invalide.' }

foreach ($functionName in @(
        'Test-ComponentLauncherRequired',
        'Get-StateSummary',
        'Get-ComponentsToStart'
    )) {
    $definition = $tree.Find({
            param($node)
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        }, $true)
    if ($null -eq $definition) { throw "Fonction introuvable : $functionName" }
    Invoke-Expression $definition.Extent.Text
}

$AllComponentNames = @('frontend')
$ComponentDefinitions = @{ frontend = @{ Label = 'Frontend'; Endpoint = 'local'; ExpectedContent = $null } }

# Doubles déterministes : aucun PID ni port réel n'est consulté.
function Get-ObjectValue {
    param($Object, $Name)
    if ($null -eq $Object) { return $null }
    if ($Object -is [System.Collections.IDictionary]) { return $Object[$Name] }
    return $Object.$Name
}
function Set-ObjectValue { param($Object, $Name, $Value); $Object.$Name = $Value }
function Get-StateComponents { param($State); return $State.components }
function Get-PrimaryRecord { param($State, $ComponentName); return $State.components.$ComponentName.listener }
function Remove-ComponentState { param($State, $ComponentName); $State.components.PSObject.Properties.Remove($ComponentName) }
function Get-EndpointExpectedContent { return $null }
function Test-Endpoint { return $true }
function Test-ProcessRecord {
    param($Record)
    if ($null -eq $Record) {
        return [pscustomobject]@{ Exists = $false; Verified = $false; Listening = $false }
    }
    return [pscustomobject]@{
        Exists = [bool]$Record.Exists
        Verified = [bool]$Record.Verified
        Listening = [bool]$Record.Listening
    }
}

if (Test-ComponentLauncherRequired -ComponentName 'frontend') {
    throw 'Le bootstrap npm est encore requis après la vérification de node.'
}
if (-not (Test-ComponentLauncherRequired -ComponentName 'backend')) {
    throw 'Le lanceur du backend a été rendu optionnel par erreur.'
}

$verifiedListener = [pscustomobject]@{ Exists = $true; Verified = $true; Listening = $true }
$ambiguousLauncher = [pscustomobject]@{ Exists = $true; Verified = $false; Listening = $false }
$activeState = [pscustomobject]@{
    components = [pscustomobject]@{
        frontend = [pscustomobject]@{ listener = $verifiedListener; launcher = $ambiguousLauncher }
    }
}
$summary = Get-StateSummary -State $activeState -ComponentNames @('frontend')
if (-not $summary.AllActive -or $summary.AllStopped) {
    throw 'Un listener node vérifié a été bloqué par le bootstrap npm ambigu.'
}

$toStart = @(Get-ComponentsToStart -State $activeState -ComponentNames @('frontend'))
if ($toStart.Count -ne 0 -or $null -ne $activeState.components.frontend.launcher) {
    throw 'L’ancien bootstrap ambigu n’a pas été détaché de l’état Frontend actif.'
}

$staleState = [pscustomobject]@{
    components = [pscustomobject]@{
        frontend = [pscustomobject]@{ listener = $null; launcher = $ambiguousLauncher }
    }
}
$summary = Get-StateSummary -State $staleState -ComponentNames @('frontend')
if (-not $summary.AllStopped) {
    throw 'Un ancien bootstrap npm sans listener empêche encore la récupération.'
}
$toStart = @(Get-ComponentsToStart -State $staleState -ComponentNames @('frontend'))
if ($toStart.Count -ne 1 -or $toStart[0] -ne 'frontend') {
    throw 'Le frontend absent n’a pas été préparé pour un nouveau démarrage.'
}

$unsafeState = [pscustomobject]@{
    components = [pscustomobject]@{
        frontend = [pscustomobject]@{
            listener = [pscustomobject]@{ Exists = $true; Verified = $false; Listening = $true }
            launcher = $ambiguousLauncher
        }
    }
}
try {
    [void](Get-ComponentsToStart -State $unsafeState -ComponentNames @('frontend'))
    throw 'Un listener node ambigu a été accepté.'
} catch {
    if ($_.Exception.Message -notmatch 'Frontend.*ambigu') { throw }
}

Write-Output 'PASS 6 cas : autorité node, backend inchangé, migration, état périmé, redémarrage, listener ambigu refusé.'
