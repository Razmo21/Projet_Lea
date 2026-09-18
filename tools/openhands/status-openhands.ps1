[CmdletBinding()]
param([switch]$Json)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Ne lit ni n'adopte l'ancien état Canvas ; seul le status SDK reste autorisé.
$result = [pscustomobject]@{
    state = 'retired'
    message = 'Agent Canvas est retiré du chemin Léa ; utilisez status-openhands-sdk.ps1.'
}
if ($Json) {
    $result | ConvertTo-Json -Compress
} else {
    Write-Host $result.message
}
