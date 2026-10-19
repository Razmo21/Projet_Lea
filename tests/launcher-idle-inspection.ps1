# Test the legacy idle-container probe in isolation, never a real Docker command.
$ErrorActionPreference = 'Stop'
$tokens = $null
$parseErrors = $null
$tree = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot '..\lea.ps1'), [ref]$tokens, [ref]$parseErrors)
if ($parseErrors) { throw 'Syntaxe du lanceur invalide.' }
$definition = $tree.Find({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-ManagedIdleAgentServer' }, $true)
Invoke-Expression $definition.Extent.Text

# Simulate native stderr with Docker unavailable; the calling Stop preference survives.
function docker.exe {
    Write-Error 'Docker unavailable (simulated)'
    $global:LASTEXITCODE = 1
}
if ($null -ne (Get-ManagedIdleAgentServer)) { throw 'Un conteneur absent a été adopté.' }
if ($ErrorActionPreference -ne 'Stop') { throw 'La préférence d’erreur du lanceur a été modifiée.' }
Write-Output 'PASS 2 cas : Docker absent non adopté, préférence Stop restaurée.'
