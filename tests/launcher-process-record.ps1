# Teste uniquement la fonction d'identité, sans exécuter les actions du lanceur.
$ErrorActionPreference = 'Stop'
$launcherPath = Join-Path $PSScriptRoot '..\lea.ps1'
$parseErrors = $null
$tokens = $null
$tree = [System.Management.Automation.Language.Parser]::ParseFile($launcherPath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors) { throw 'Syntaxe du lanceur invalide.' }
$definition = $tree.Find({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Test-ProcessRecord' }, $true)
Invoke-Expression $definition.Extent.Text

# Doubles en lecture seule : aucun PID réel n'est ciblé par cette suite.
function Get-Process { param($Id) return $script:fakeProcess }
function Get-ObjectValue { param($Object, $Name) return $Object.$Name }
function Get-ProcessPath { param($Process) return $Process.Path }
function Test-SamePath { param($Left, $Right) return $Left -ieq $Right }
function Get-ListeningPids { param($Port) return @(1234) }

$record = [pscustomobject]@{
    pid = 1234; processName = 'python'; executablePath = 'C:\test\python.exe'
    startTimeUtc = '2026-10-17T08:00:00.0000000Z'; port = 8000
}
$script:fakeProcess = [pscustomobject]@{
    Id = 1234; ProcessName = 'python'; Path = 'C:\test\python.exe'; HasExited = $false
    StartTime = [datetime]::Parse($record.startTimeUtc)
}
$check = Test-ProcessRecord $record
if (-not ($check.Exists -and $check.Verified -and $check.Listening)) { throw 'Identité valide refusée.' }

# Même nom et même port ne permettent pas d'adopter un PID recyclé.
$script:fakeProcess.StartTime = $script:fakeProcess.StartTime.AddHours(1)
$check = Test-ProcessRecord $record
if ($check.Exists -or $check.Verified -or $check.Listening -or $null -ne $check.Process) { throw 'PID recyclé adopté.' }

# Une date inaccessible ou un chemin différent ne doit pas devenir une absence.
$script:fakeProcess.StartTime = $null
$check = Test-ProcessRecord $record
if (-not $check.Exists -or $check.Verified) { throw 'Date inconnue non bloquante.' }
$script:fakeProcess.StartTime = [datetime]::Parse($record.startTimeUtc)
$script:fakeProcess.Path = 'C:\other\python.exe'
$check = Test-ProcessRecord $record
if (-not $check.Exists -or $check.Verified) { throw 'Exécutable étranger accepté.' }

$script:fakeProcess.HasExited = $true
if ((Test-ProcessRecord $record).Exists) { throw 'Processus terminé encore présent.' }
if ((Test-ProcessRecord $null).Exists) { throw 'Record absent adopté.' }
Write-Output 'PASS 6 cas : identité, PID recyclé, date inconnue, chemin étranger, processus terminé, record absent.'
