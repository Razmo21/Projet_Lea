param(
    [Parameter(Position = 0)]
    [string]$Action
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$ProjectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$StateDirectory = Join-Path $ProjectRoot '.lea'
$StateFile = Join-Path $StateDirectory 'processes.json'
$TaskkillExecutable = Join-Path $env:SystemRoot 'System32\taskkill.exe'
$NetstatExecutable = Join-Path $env:SystemRoot 'System32\netstat.exe'

$ModelExecutable = Join-Path $ProjectRoot 'runtime\llama.cpp\llama-server.exe'
$ModelPath = Join-Path $ProjectRoot 'models\general\Qwen3-4B-Q4_K_M.gguf'
$BackendDirectory = Join-Path $ProjectRoot 'backend'
$BackendPython = Join-Path $BackendDirectory '.venv\Scripts\python.exe'
$PackageFile = Join-Path $ProjectRoot 'package.json'

$ComponentDefinitions = [ordered]@{
    model = [ordered]@{
        Label = 'Modèle'
        Port = 8080
        ExpectedName = 'llama-server'
        ExpectedPath = $ModelExecutable
        Endpoint = 'http://127.0.0.1:8080/v1/models'
        ExpectedContent = 'lea-general'
    }
    backend = [ordered]@{
        Label = 'Backend'
        Port = 8000
        ExpectedName = 'python'
        ExpectedPath = $BackendPython
        Endpoint = 'http://127.0.0.1:8000/health'
        ExpectedContent = '"status":"ok"'
    }
    frontend = [ordered]@{
        Label = 'Frontend'
        Port = 5173
        ExpectedName = 'node'
        ExpectedPath = $null
        Endpoint = 'http://127.0.0.1:5173'
        ExpectedContent = $null
    }
}

$KnownStateFiles = @(
    'processes.json',
    'model.stdout.log',
    'model.stderr.log',
    'backend.stdout.log',
    'backend.stderr.log',
    'frontend.stdout.log',
    'frontend.stderr.log'
)

function Get-ParentProcessId {
    param([Parameter(Mandatory = $true)][int]$ProcessId)

    if ($null -eq ('LeaProcessTree' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

public static class LeaProcessTree
{
    private const uint TH32CS_SNAPPROCESS = 0x00000002;
    private static readonly IntPtr INVALID_HANDLE_VALUE = new IntPtr(-1);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Auto)]
    private struct PROCESSENTRY32
    {
        public uint dwSize;
        public uint cntUsage;
        public uint th32ProcessID;
        public IntPtr th32DefaultHeapID;
        public uint th32ModuleID;
        public uint cntThreads;
        public uint th32ParentProcessID;
        public int pcPriClassBase;
        public uint dwFlags;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)]
        public string szExeFile;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr CreateToolhelp32Snapshot(uint dwFlags, uint th32ProcessID);

    [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    private static extern bool Process32First(IntPtr hSnapshot, ref PROCESSENTRY32 lppe);

    [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    private static extern bool Process32Next(IntPtr hSnapshot, ref PROCESSENTRY32 lppe);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool CloseHandle(IntPtr hObject);

    public static int GetParentProcessId(int processId)
    {
        IntPtr snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
        if (snapshot == INVALID_HANDLE_VALUE)
        {
            return 0;
        }

        try
        {
            PROCESSENTRY32 entry = new PROCESSENTRY32();
            entry.dwSize = (uint)Marshal.SizeOf(typeof(PROCESSENTRY32));
            bool found = Process32First(snapshot, ref entry);
            while (found)
            {
                if (entry.th32ProcessID == (uint)processId)
                {
                    return (int)entry.th32ParentProcessID;
                }

                found = Process32Next(snapshot, ref entry);
            }

            return 0;
        }
        finally
        {
            CloseHandle(snapshot);
        }
    }

    public static int[] GetDescendantProcessIds(int rootProcessId)
    {
        IntPtr snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
        if (snapshot == INVALID_HANDLE_VALUE)
        {
            return new int[0];
        }

        try
        {
            Dictionary<int, List<int>> childrenByParent = new Dictionary<int, List<int>>();
            PROCESSENTRY32 entry = new PROCESSENTRY32();
            entry.dwSize = (uint)Marshal.SizeOf(typeof(PROCESSENTRY32));
            bool found = Process32First(snapshot, ref entry);
            while (found)
            {
                int parentProcessId = (int)entry.th32ParentProcessID;
                List<int> children;
                if (!childrenByParent.TryGetValue(parentProcessId, out children))
                {
                    children = new List<int>();
                    childrenByParent.Add(parentProcessId, children);
                }

                children.Add((int)entry.th32ProcessID);
                found = Process32Next(snapshot, ref entry);
            }

            List<int> descendants = new List<int>();
            Queue<int> pendingParents = new Queue<int>();
            pendingParents.Enqueue(rootProcessId);
            while (pendingParents.Count > 0)
            {
                int parentProcessId = pendingParents.Dequeue();
                List<int> children;
                if (!childrenByParent.TryGetValue(parentProcessId, out children))
                {
                    continue;
                }

                foreach (int childProcessId in children)
                {
                    descendants.Add(childProcessId);
                    pendingParents.Enqueue(childProcessId);
                }
            }

            return descendants.ToArray();
        }
        finally
        {
            CloseHandle(snapshot);
        }
    }
}
'@
    }

    try {
        return [LeaProcessTree]::GetParentProcessId($ProcessId)
    } catch {
        return 0
    }
}

function Test-ProcessDescendsFrom {
    param(
        [Parameter(Mandatory = $true)][int]$ChildProcessId,
        [Parameter(Mandatory = $true)][int]$AncestorProcessId
    )

    if ($ChildProcessId -eq $AncestorProcessId) {
        return $true
    }

    $visited = New-Object 'System.Collections.Generic.HashSet[int]'
    $currentProcessId = $ChildProcessId
    while ($currentProcessId -gt 0 -and $visited.Add($currentProcessId)) {
        $parentProcessId = Get-ParentProcessId -ProcessId $currentProcessId
        if ($parentProcessId -eq $AncestorProcessId) {
            return $true
        }

        $currentProcessId = $parentProcessId
    }

    return $false
}

function Get-DescendantProcessIds {
    param([Parameter(Mandatory = $true)][int]$RootProcessId)

    if ($null -eq ('LeaProcessTree' -as [type])) {
        [void](Get-ParentProcessId -ProcessId $RootProcessId)
    }

    try {
        return @([LeaProcessTree]::GetDescendantProcessIds($RootProcessId) | Sort-Object -Unique)
    } catch {
        throw "Impossible de vérifier l’arbre de processus de Léa : $($_.Exception.Message)"
    }
}

function Assert-ListenerBelongsToLauncher {
    param(
        [Parameter(Mandatory = $true)][int]$ListenerProcessId,
        [Parameter(Mandatory = $true)][int]$LauncherProcessId,
        [Parameter(Mandatory = $true)][string]$ComponentLabel
    )

    if (-not (Test-ProcessDescendsFrom -ChildProcessId $ListenerProcessId -AncestorProcessId $LauncherProcessId)) {
        throw "Le PID d’écoute $ListenerProcessId de $ComponentLabel n’appartient pas à l’arbre du processus lancé ($LauncherProcessId)."
    }
}

function Write-Usage {
    Write-Host 'Usage:'
    Write-Host '  .\lea.ps1 start'
    Write-Host '  .\lea.ps1 status'
    Write-Host '  .\lea.ps1 stop'
}

function Get-ObjectValue {
    param(
        $Object,
        [Parameter(Mandatory = $true)][string]$Name
    )

    if ($null -eq $Object) {
        return $null
    }

    if ($Object -is [System.Collections.IDictionary]) {
        if ($Object.Contains($Name)) {
            return $Object[$Name]
        }

        return $null
    }

    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return $null
    }

    return $property.Value
}

function Test-SamePath {
    param(
        [string]$Left,
        [string]$Right
    )

    if ([string]::IsNullOrWhiteSpace($Left) -or [string]::IsNullOrWhiteSpace($Right)) {
        return $false
    }

    try {
        $normalLeft = [System.IO.Path]::GetFullPath($Left)
        $normalRight = [System.IO.Path]::GetFullPath($Right)
    } catch {
        return $false
    }

    return [string]::Equals(
        $normalLeft,
        $normalRight,
        [System.StringComparison]::OrdinalIgnoreCase
    )
}

function Get-ListeningPids {
    param([Parameter(Mandatory = $true)][int]$Port)

    $pattern = '^\s*TCP\s+\S+:' + [regex]::Escape([string]$Port) + '\s+\S+\s+LISTENING\s+(?<pid>\d+)\s*$'
    $pids = @()

    foreach ($line in @(& $NetstatExecutable -ano -p tcp 2>$null)) {
        if ($line -match $pattern) {
            $pids += [int]$Matches['pid']
        }
    }

    return @($pids | Sort-Object -Unique)
}

function Assert-PortFree {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][string]$ComponentLabel
    )

    $pids = @(Get-ListeningPids -Port $Port)
    if ($pids.Count -gt 0) {
        throw "Impossible de démarrer Léa : le port $Port pour $ComponentLabel est déjà utilisé par un autre processus (PID $($pids -join ', '))."
    }
}

function Get-ProcessPath {
    param([Parameter(Mandatory = $true)][System.Diagnostics.Process]$Process)

    try {
        return $Process.Path
    } catch {
        return $null
    }
}

function New-ProcessRecord {
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [string]$ExpectedName,
        [string]$ExpectedPath,
        [int]$Port = 0
    )

    $process = Get-Process -Id $ProcessId -ErrorAction Stop
    if (-not [string]::IsNullOrWhiteSpace($ExpectedName) -and $process.ProcessName -ine $ExpectedName) {
        throw "Le processus $ProcessId n’est pas le composant attendu ($ExpectedName)."
    }

    $actualPath = Get-ProcessPath -Process $process
    if (
        -not [string]::IsNullOrWhiteSpace($ExpectedPath) -and
        -not [string]::IsNullOrWhiteSpace($actualPath) -and
        -not (Test-SamePath -Left $actualPath -Right $ExpectedPath)
    ) {
        throw "Le processus $ProcessId n’utilise pas l’exécutable attendu."
    }

    if ([string]::IsNullOrWhiteSpace($ExpectedPath)) {
        $ExpectedPath = $actualPath
    }

    return [ordered]@{
        pid = [int]$process.Id
        processName = $process.ProcessName
        executablePath = $ExpectedPath
        startTimeUtc = $process.StartTime.ToUniversalTime().ToString('o')
        port = [int]$Port
    }
}

function Test-ProcessRecord {
    param($Record)

    if ($null -eq $Record) {
        return [pscustomobject]@{
            Exists = $false
            Verified = $false
            Listening = $false
            Process = $null
            Reason = 'Aucun PID enregistré.'
        }
    }

    $recordedProcessId = [int](Get-ObjectValue -Object $Record -Name 'pid')
    try {
        $process = Get-Process -Id $recordedProcessId -ErrorAction Stop
    } catch {
        return [pscustomobject]@{
            Exists = $false
            Verified = $false
            Listening = $false
            Process = $null
            Reason = "Le PID enregistré n’existe plus."
        }
    }

    $processHasExited = $false
    try {
        $processHasExited = $process.HasExited
    } catch {
        # Impossible de confirmer la fin du processus : les vérifications suivantes restent fail-closed.
    }

    if ($processHasExited) {
        return [pscustomobject]@{
            Exists = $false
            Verified = $false
            Listening = $false
            Process = $null
            Reason = "Le PID enregistré est déjà terminé."
        }
    }

    $nameMatches = $process.ProcessName -ieq [string](Get-ObjectValue -Object $Record -Name 'processName')
    $timeMatches = $false
    try {
        $recordedStart = [datetime]::Parse([string](Get-ObjectValue -Object $Record -Name 'startTimeUtc')).ToUniversalTime()
        $actualStart = $process.StartTime.ToUniversalTime()
        $timeMatches = [math]::Abs(($actualStart - $recordedStart).TotalSeconds) -lt 1
    } catch {
        $timeMatches = $false
    }

    $pathMatches = $true
    $expectedPath = [string](Get-ObjectValue -Object $Record -Name 'executablePath')
    $actualPath = Get-ProcessPath -Process $process
    if (-not [string]::IsNullOrWhiteSpace($expectedPath) -and -not [string]::IsNullOrWhiteSpace($actualPath)) {
        $pathMatches = Test-SamePath -Left $actualPath -Right $expectedPath
    }

    $port = [int](Get-ObjectValue -Object $Record -Name 'port')
    $listening = $false
    if ($port -gt 0) {
        $listening = @(Get-ListeningPids -Port $port) -contains $recordedProcessId
    }

    $verified = $nameMatches -and $timeMatches -and $pathMatches
    $reason = 'Identité vérifiée.'
    if (-not $verified) {
        $reason = "Le nom, le chemin ou l’heure de démarrage ne correspondent pas à l’état enregistré."
    }

    return [pscustomobject]@{
        Exists = $true
        Verified = $verified
        Listening = $listening
        Process = $process
        Reason = $reason
    }
}

function Initialize-StateDirectory {
    if (-not (Test-Path -LiteralPath $StateDirectory)) {
        New-Item -ItemType Directory -Path $StateDirectory -Force | Out-Null
    }
}

function Read-LeaState {
    if (-not (Test-Path -LiteralPath $StateFile)) {
        return $null
    }

    try {
        $state = Get-Content -LiteralPath $StateFile -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        throw "L’état temporaire de Léa est illisible : $StateFile"
    }

    $recordedRoot = [string](Get-ObjectValue -Object $state -Name 'projectRoot')
    if (-not (Test-SamePath -Left $recordedRoot -Right $ProjectRoot)) {
        throw "L’état temporaire ne correspond pas à ce projet. Aucun processus ne sera arrêté automatiquement."
    }

    return $state
}

function Write-LeaState {
    param([Parameter(Mandatory = $true)]$State)

    Initialize-StateDirectory
    $State | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $StateFile -Encoding UTF8
}

function Remove-LeaState {
    param([switch]$KeepLogs)

    if (Test-Path -LiteralPath $StateFile) {
        Remove-Item -LiteralPath $StateFile -Force
    }

    if (-not $KeepLogs -and (Test-Path -LiteralPath $StateDirectory)) {
        foreach ($fileName in $KnownStateFiles) {
            $filePath = Join-Path $StateDirectory $fileName
            if (Test-Path -LiteralPath $filePath) {
                Remove-Item -LiteralPath $filePath -Force
            }
        }

        $remainingFiles = @(Get-ChildItem -LiteralPath $StateDirectory -Force -ErrorAction SilentlyContinue)
        if ($remainingFiles.Count -eq 0) {
            Remove-Item -LiteralPath $StateDirectory -Force
        }
    }
}

function Clear-PreviousLogs {
    Initialize-StateDirectory
    foreach ($fileName in ($KnownStateFiles | Where-Object { $_ -ne 'processes.json' })) {
        $filePath = Join-Path $StateDirectory $fileName
        if (Test-Path -LiteralPath $filePath) {
            Remove-Item -LiteralPath $filePath -Force
        }
    }
}

function New-LeaState {
    return [ordered]@{
        version = 1
        projectRoot = $ProjectRoot
        phase = 'starting'
        components = [ordered]@{}
    }
}

function Get-PrimaryRecord {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)][string]$ComponentName
    )

    $components = Get-ObjectValue -Object $State -Name 'components'
    $component = Get-ObjectValue -Object $components -Name $ComponentName
    if ($null -eq $component) {
        return $null
    }

    return Get-ObjectValue -Object $component -Name 'listener'
}

function Test-Endpoint {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [string]$ExpectedContent
    )

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 5
        if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 300) {
            return $false
        }

        if (-not [string]::IsNullOrWhiteSpace($ExpectedContent) -and $response.Content -notmatch $ExpectedContent) {
            return $false
        }

        return $true
    } catch {
        return $false
    }
}

function Wait-ForEndpoint {
    param(
        [Parameter(Mandatory = $true)][string]$ComponentLabel,
        [Parameter(Mandatory = $true)][string]$Uri,
        [string]$ExpectedContent,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )

    $deadline = [datetime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([datetime]::UtcNow -lt $deadline) {
        if (Test-Endpoint -Uri $Uri -ExpectedContent $ExpectedContent) {
            return
        }

        Start-Sleep -Milliseconds 500
    }

    throw "$ComponentLabel n’est pas prêt après $TimeoutSeconds secondes. Consultez les journaux dans $StateDirectory."
}

function Assert-RecordOwnsPort {
    param(
        [Parameter(Mandatory = $true)]$Record,
        [Parameter(Mandatory = $true)][string]$ComponentLabel
    )

    $port = [int](Get-ObjectValue -Object $Record -Name 'port')
    $recordedProcessId = [int](Get-ObjectValue -Object $Record -Name 'pid')
    if (@(Get-ListeningPids -Port $port) -notcontains $recordedProcessId) {
        throw "$ComponentLabel est prêt, mais le PID enregistré ne possède pas le port $port."
    }
}

function Stop-JustStartedProcess {
    param([System.Diagnostics.Process]$Process)

    if ($null -eq $Process) {
        return
    }

    try {
        $originalName = $Process.ProcessName
        $originalPath = Get-ProcessPath -Process $Process
        $originalStartTime = $Process.StartTime.ToUniversalTime().ToString('o')
    } catch {
        return
    }

    $record = [ordered]@{
        pid = [int]$Process.Id
        processName = $originalName
        executablePath = $originalPath
        startTimeUtc = $originalStartTime
        port = 0
    }

    $check = Test-ProcessRecord -Record $record
    if (-not $check.Exists) {
        return
    }

    if (-not $check.Verified) {
        throw "Refus d’arrêter le processus lancé $($Process.Id) : son identité a changé."
    }

    Stop-ManagedRecord -Record $record -ComponentLabel "processus lancé $($Process.Id)"
}

function Start-Model {
    param([Parameter(Mandatory = $true)]$State)

    $definition = $ComponentDefinitions.model
    Assert-PortFree -Port $definition.Port -ComponentLabel $definition.Label
    Write-Host 'Démarrage du modèle local...'

    $arguments = '-m "' + $ModelPath + '" -ngl 99 -c 4096 --host 127.0.0.1 --port 8080 --jinja --alias lea-general'
    $process = $null
    try {
        $process = Start-Process -FilePath $ModelExecutable -ArgumentList $arguments -WorkingDirectory $ProjectRoot -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $StateDirectory 'model.stdout.log') -RedirectStandardError (Join-Path $StateDirectory 'model.stderr.log')
        $launcherRecord = New-ProcessRecord -ProcessId $process.Id -ExpectedName $definition.ExpectedName -ExpectedPath $definition.ExpectedPath
        $State.components['model'] = [ordered]@{
            launcher = $launcherRecord
            listener = $null
        }
        Write-LeaState -State $State
        Wait-ForEndpoint -ComponentLabel $definition.Label -Uri $definition.Endpoint -ExpectedContent $definition.ExpectedContent -TimeoutSeconds 120
        $listenerPids = @(Get-ListeningPids -Port $definition.Port)
        if ($listenerPids.Count -ne 1) {
            throw "Le modèle n’a pas un PID d’écoute unique sur le port $($definition.Port)."
        }

        Assert-ListenerBelongsToLauncher -ListenerProcessId $listenerPids[0] -LauncherProcessId $process.Id -ComponentLabel $definition.Label
        $listenerRecord = New-ProcessRecord -ProcessId $listenerPids[0] -ExpectedName $definition.ExpectedName -ExpectedPath $definition.ExpectedPath -Port $definition.Port
        $State.components['model']['listener'] = $listenerRecord
        Write-LeaState -State $State
        Assert-RecordOwnsPort -Record $listenerRecord -ComponentLabel $definition.Label
    } catch {
        if ($null -ne $process -and $null -eq (Get-ObjectValue -Object (Get-ObjectValue -Object $State -Name 'components') -Name 'model')) {
            Stop-JustStartedProcess -Process $process
        }

        throw
    }
}

function Start-Backend {
    param([Parameter(Mandatory = $true)]$State)

    $definition = $ComponentDefinitions.backend
    Assert-PortFree -Port $definition.Port -ComponentLabel $definition.Label
    Write-Host 'Démarrage du backend FastAPI...'

    $process = $null
    try {
        $process = Start-Process -FilePath $BackendPython -ArgumentList '-m uvicorn app.main:app --host 127.0.0.1 --port 8000' -WorkingDirectory $BackendDirectory -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $StateDirectory 'backend.stdout.log') -RedirectStandardError (Join-Path $StateDirectory 'backend.stderr.log')
        $launcherRecord = New-ProcessRecord -ProcessId $process.Id -ExpectedName $definition.ExpectedName -ExpectedPath $definition.ExpectedPath
        $State.components['backend'] = [ordered]@{
            launcher = $launcherRecord
            listener = $null
        }
        Write-LeaState -State $State
        Wait-ForEndpoint -ComponentLabel $definition.Label -Uri $definition.Endpoint -ExpectedContent $definition.ExpectedContent -TimeoutSeconds 30
        $listenerPids = @(Get-ListeningPids -Port $definition.Port)
        if ($listenerPids.Count -ne 1) {
            throw "Le backend n’a pas un PID d’écoute unique sur le port $($definition.Port)."
        }

        Assert-ListenerBelongsToLauncher -ListenerProcessId $listenerPids[0] -LauncherProcessId $process.Id -ComponentLabel $definition.Label
        $listenerRecord = New-ProcessRecord -ProcessId $listenerPids[0] -ExpectedName $definition.ExpectedName -ExpectedPath $null -Port $definition.Port
        $State.components['backend']['listener'] = $listenerRecord
        Write-LeaState -State $State
        Assert-RecordOwnsPort -Record $listenerRecord -ComponentLabel $definition.Label
    } catch {
        if ($null -ne $process -and $null -eq (Get-ObjectValue -Object (Get-ObjectValue -Object $State -Name 'components') -Name 'backend')) {
            Stop-JustStartedProcess -Process $process
        }

        throw
    }
}

function Start-Frontend {
    param([Parameter(Mandatory = $true)]$State)

    $definition = $ComponentDefinitions.frontend
    Assert-PortFree -Port $definition.Port -ComponentLabel $definition.Label
    Write-Host 'Démarrage du frontend Vite...'

    $npmCommand = (Get-Command npm.cmd -ErrorAction Stop).Source
    $process = $null
    try {
        $process = Start-Process -FilePath $npmCommand -ArgumentList 'run dev -- --host 127.0.0.1 --port 5173' -WorkingDirectory $ProjectRoot -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $StateDirectory 'frontend.stdout.log') -RedirectStandardError (Join-Path $StateDirectory 'frontend.stderr.log')
        $launcherRecord = New-ProcessRecord -ProcessId $process.Id -ExpectedName $process.ProcessName -ExpectedPath (Get-ProcessPath -Process $process)
        $State.components['frontend'] = [ordered]@{
            launcher = $launcherRecord
            listener = $null
        }
        Write-LeaState -State $State
        Wait-ForEndpoint -ComponentLabel $definition.Label -Uri $definition.Endpoint -ExpectedContent $definition.ExpectedContent -TimeoutSeconds 30
        $listenerPids = @(Get-ListeningPids -Port $definition.Port)
        if ($listenerPids.Count -ne 1) {
            throw "Le frontend n’a pas un PID d’écoute unique sur le port $($definition.Port)."
        }

        Assert-ListenerBelongsToLauncher -ListenerProcessId $listenerPids[0] -LauncherProcessId $process.Id -ComponentLabel $definition.Label
        $listenerRecord = New-ProcessRecord -ProcessId $listenerPids[0] -ExpectedName $definition.ExpectedName -ExpectedPath $null -Port $definition.Port
        $State.components['frontend']['listener'] = $listenerRecord
        Write-LeaState -State $State
        Assert-RecordOwnsPort -Record $listenerRecord -ComponentLabel $definition.Label
    } catch {
        $frontendState = Get-ObjectValue -Object (Get-ObjectValue -Object $State -Name 'components') -Name 'frontend'
        if ($null -eq (Get-ObjectValue -Object $frontendState -Name 'listener')) {
            Stop-JustStartedProcess -Process $process
        }

        throw
    }
}

function Get-StateSummary {
    param([Parameter(Mandatory = $true)]$State)

    $items = [ordered]@{}
    $allActive = $true
    $allStopped = $true

    foreach ($componentName in @('model', 'backend', 'frontend')) {
        $record = Get-PrimaryRecord -State $State -ComponentName $componentName
        $check = Test-ProcessRecord -Record $record
        $componentState = Get-ObjectValue -Object (Get-ObjectValue -Object $State -Name 'components') -Name $componentName
        $launcherRecord = Get-ObjectValue -Object $componentState -Name 'launcher'
        $launcherCheck = Test-ProcessRecord -Record $launcherRecord
        $active = $check.Exists -and $check.Verified -and $check.Listening
        $items[$componentName] = [pscustomobject]@{
            Record = $record
            Check = $check
            LauncherRecord = $launcherRecord
            LauncherCheck = $launcherCheck
            Active = $active
        }

        $componentFullyActive = $active -and $launcherCheck.Exists -and $launcherCheck.Verified
        if (-not $componentFullyActive) {
            $allActive = $false
        }

        if ($check.Exists -or $launcherCheck.Exists) {
            $allStopped = $false
        }
    }

    return [pscustomobject]@{
        Items = $items
        AllActive = $allActive
        AllStopped = $allStopped
    }
}

function Test-AllEndpointsReady {
    foreach ($componentName in @('model', 'backend', 'frontend')) {
        $definition = $ComponentDefinitions[$componentName]
        if (-not (Test-Endpoint -Uri $definition.Endpoint -ExpectedContent $definition.ExpectedContent)) {
            return $false
        }
    }

    return $true
}

function Write-LeaStatus {
    param($State)

    Write-Host 'Léa'
    if ($null -eq $State) {
        foreach ($componentName in @('model', 'backend', 'frontend')) {
            $definition = $ComponentDefinitions[$componentName]
            $owners = @(Get-ListeningPids -Port $definition.Port)
            if ($owners.Count -eq 0) {
                Write-Host ("{0,-10}: arrêté" -f $definition.Label)
            } else {
                Write-Host ("{0,-10}: inconnu (port {1} occupé par PID {2})" -f $definition.Label, $definition.Port, ($owners -join ', '))
            }
        }

        return
    }

    $summary = Get-StateSummary -State $State
    foreach ($componentName in @('model', 'backend', 'frontend')) {
        $definition = $ComponentDefinitions[$componentName]
        $item = $summary.Items[$componentName]
        if ($item.Active -and $item.LauncherCheck.Exists -and $item.LauncherCheck.Verified) {
            Write-Host ("{0,-10}: actif (PID {1})" -f $definition.Label, (Get-ObjectValue -Object $item.Record -Name 'pid'))
        } elseif ($item.LauncherCheck.Exists -and $item.LauncherCheck.Verified -and $null -eq $item.Record) {
            Write-Host ("{0,-10}: démarrage en cours" -f $definition.Label)
        } elseif (-not $item.Check.Exists) {
            Write-Host ("{0,-10}: arrêté" -f $definition.Label)
        } else {
            Write-Host ("{0,-10}: état incohérent — {1}" -f $definition.Label, $item.Check.Reason)
        }
    }

    if ($summary.AllActive) {
        Write-Host 'Interface : http://127.0.0.1:5173'
    }
}

function Stop-ManagedRecord {
    param(
        $Record,
        [Parameter(Mandatory = $true)][string]$ComponentLabel
    )

    if ($null -eq $Record) {
        return
    }

    $check = Test-ProcessRecord -Record $Record
    if (-not $check.Exists) {
        return
    }

    if (-not $check.Verified) {
        throw "Refus d’arrêter $ComponentLabel : l’identité du PID enregistré est ambiguë."
    }

    $process = $check.Process
    try {
        if ($process.CloseMainWindow()) {
            Start-Sleep -Seconds 2
        }
    } catch {
        # Les services de cette étape sont généralement sans fenêtre principale.
    }

    $check = Test-ProcessRecord -Record $Record
    if (-not $check.Exists) {
        return
    }

    if (-not $check.Verified) {
        throw "Refus d’arrêter $ComponentLabel : l’identité du PID enregistré a changé."
    }

    $process = $check.Process

    $taskkillSucceeded = $false
    try {
        & $TaskkillExecutable /PID $process.Id /T /F 2>$null | Out-Null
        $taskkillSucceeded = $LASTEXITCODE -eq 0
    } catch {
        $taskkillSucceeded = $false
    }

    if (-not $taskkillSucceeded) {
        $check = Test-ProcessRecord -Record $Record
        if (-not $check.Exists) {
            return
        }

        if (-not $check.Verified) {
            throw "Refus d’arrêter $ComponentLabel : l’identité du PID enregistré a changé."
        }

        $descendantRecords = @()
        foreach ($descendantProcessId in @(Get-DescendantProcessIds -RootProcessId $check.Process.Id)) {
            try {
                $descendantProcess = Get-Process -Id $descendantProcessId -ErrorAction Stop
                $descendantRecord = New-ProcessRecord -ProcessId $descendantProcess.Id -ExpectedName $descendantProcess.ProcessName -ExpectedPath (Get-ProcessPath -Process $descendantProcess)
                $descendantRecords += ,$descendantRecord
            } catch {
                # Le descendant a disparu avant son enregistrement ; il n’y a rien à arrêter.
            }
        }

        $check = Test-ProcessRecord -Record $Record
        if (-not $check.Exists) {
            return
        }

        if (-not $check.Verified) {
            throw "Refus d’arrêter $ComponentLabel : l’identité du PID enregistré a changé."
        }

        try {
            $check.Process | Stop-Process -Force -ErrorAction Stop
        } catch {
            # Le processus a déjà été arrêté.
        }

        foreach ($descendantRecord in $descendantRecords) {
            Stop-VerifiedRecordDirectly -Record $descendantRecord -ComponentLabel "$ComponentLabel (processus enfant)"
        }
    }

    $deadline = [datetime]::UtcNow.AddSeconds(10)
    while ([datetime]::UtcNow -lt $deadline) {
        $check = Test-ProcessRecord -Record $Record
        if (-not $check.Exists -or -not $check.Verified) {
            return
        }

        Start-Sleep -Milliseconds 250
    }

    throw "$ComponentLabel n’a pas pu être arrêté."
}

function Stop-VerifiedRecordDirectly {
    param(
        $Record,
        [Parameter(Mandatory = $true)][string]$ComponentLabel
    )

    if ($null -eq $Record) {
        return
    }

    $check = Test-ProcessRecord -Record $Record
    if (-not $check.Exists) {
        return
    }

    if (-not $check.Verified) {
        throw "Refus d’arrêter $ComponentLabel : l’identité du PID enregistré est ambiguë."
    }

    try {
        $check.Process | Stop-Process -Force -ErrorAction Stop
    } catch {
        # Le processus a pu se terminer entre la vérification et l’arrêt.
    }

    $deadline = [datetime]::UtcNow.AddSeconds(10)
    while ([datetime]::UtcNow -lt $deadline) {
        $check = Test-ProcessRecord -Record $Record
        if (-not $check.Exists) {
            return
        }

        if (-not $check.Verified) {
            # Le PID d’origine a disparu puis a été réemployé : ne jamais toucher au nouveau processus.
            return
        }

        Start-Sleep -Milliseconds 250
    }

    throw "$ComponentLabel n’a pas pu être arrêté."
}

function Confirm-ModelVramReleased {
    param([int]$ModelPid)

    try {
        $gpuProcesses = @(& nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>$null)
        if ($LASTEXITCODE -ne 0) {
            throw 'nvidia-smi a retourné une erreur.'
        }

        $modelPidPattern = '^\s*' + [regex]::Escape([string]$ModelPid) + '\s*$'
        if ($gpuProcesses -match $modelPidPattern) {
            Write-Warning 'Le PID du modèle est encore signalé par nvidia-smi.'
        } else {
            Write-Host 'VRAM : libérée pour le modèle Léa.'
        }
    } catch {
        Write-Host 'VRAM : vérification indisponible, mais le processus modèle est arrêté.'
    }
}

function Stop-ComponentFromState {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)][string]$ComponentName,
        [Parameter(Mandatory = $true)][string]$ComponentLabel
    )

    $components = Get-ObjectValue -Object $State -Name 'components'
    $component = Get-ObjectValue -Object $components -Name $ComponentName
    $listener = Get-ObjectValue -Object $component -Name 'listener'
    $launcher = Get-ObjectValue -Object $component -Name 'launcher'
    $launcherCheck = Test-ProcessRecord -Record $launcher

    Write-Host "Arrêt du $ComponentLabel..."

    if ($launcherCheck.Exists -and $launcherCheck.Verified) {
        Stop-ManagedRecord -Record $launcher -ComponentLabel $ComponentLabel
    }

    Stop-ManagedRecord -Record $listener -ComponentLabel $ComponentLabel
}

function Stop-LeaFromState {
    param(
        [Parameter(Mandatory = $true)]$State,
        [switch]$KeepLogs
    )

    $summary = Get-StateSummary -State $State
    foreach ($componentName in @('model', 'backend', 'frontend')) {
        $item = $summary.Items[$componentName]
        if ($item.Check.Exists -and -not $item.Check.Verified) {
            $definition = $ComponentDefinitions[$componentName]
            throw "Refus d’arrêter Léa : l’état de $($definition.Label) est ambigu. Aucun processus ne sera tué."
        }

        if ($item.LauncherCheck.Exists -and -not $item.LauncherCheck.Verified) {
            $definition = $ComponentDefinitions[$componentName]
            throw "Refus d’arrêter Léa : l’état du lanceur de $($definition.Label) est ambigu. Aucun processus ne sera tué."
        }
    }

    $modelRecord = $summary.Items.model.Record
    if ($null -eq $modelRecord) {
        $modelRecord = $summary.Items.model.LauncherRecord
    }
    $modelPid = $null
    if ($null -ne $modelRecord) {
        $modelPid = [int](Get-ObjectValue -Object $modelRecord -Name 'pid')
    }

    $stopErrors = @()
    foreach ($componentToStop in @(
            [pscustomobject]@{ Name = 'frontend'; Label = 'frontend Vite' },
            [pscustomobject]@{ Name = 'backend'; Label = 'backend FastAPI' },
            [pscustomobject]@{ Name = 'model'; Label = 'modèle local' }
        )) {
        try {
            Stop-ComponentFromState -State $State -ComponentName $componentToStop.Name -ComponentLabel $componentToStop.Label
        } catch {
            $stopErrors += "$($componentToStop.Label) : $($_.Exception.Message)"
        }
    }

    foreach ($componentName in @('frontend', 'backend', 'model')) {
        $definition = $ComponentDefinitions[$componentName]
        $owners = @(Get-ListeningPids -Port $definition.Port)
        if ($owners.Count -eq 0) {
            Write-Host "Port $($definition.Port) libéré."
        } else {
            $portMessage = "Le port $($definition.Port) reste utilisé par le PID $($owners -join ', '). Aucun processus inconnu n’a été arrêté."
            Write-Warning $portMessage
            $stopErrors += $portMessage
        }
    }

    $remainingSummary = Get-StateSummary -State $State
    foreach ($componentName in @('model', 'backend', 'frontend')) {
        $remainingItem = $remainingSummary.Items[$componentName]
        if ($remainingItem.Check.Exists -or $remainingItem.LauncherCheck.Exists) {
            $definition = $ComponentDefinitions[$componentName]
            $stopErrors += "Le processus enregistré de $($definition.Label) est encore présent."
        }
    }

    if ($stopErrors.Count -gt 0) {
        throw "Arrêt incomplet. L’état et les journaux sont conservés pour éviter de perdre la trace des processus : $($stopErrors -join ' | ')"
    }

    if ($null -ne $modelPid) {
        Confirm-ModelVramReleased -ModelPid $modelPid
    }

    Remove-LeaState -KeepLogs:$KeepLogs
}

function Assert-RequiredFiles {
    $requiredFiles = @(
        [pscustomobject]@{ Description = 'llama-server.exe'; Path = $ModelExecutable },
        [pscustomobject]@{ Description = 'le modèle Qwen'; Path = $ModelPath },
        [pscustomobject]@{ Description = 'le Python de backend/.venv'; Path = $BackendPython },
        [pscustomobject]@{ Description = 'package.json'; Path = $PackageFile }
    )

    foreach ($requiredFile in $requiredFiles) {
        if (-not (Test-Path -LiteralPath $requiredFile.Path -PathType Leaf)) {
            throw "Fichier requis introuvable : $($requiredFile.Path) ($($requiredFile.Description))."
        }
    }

    try {
        Get-Command npm.cmd -ErrorAction Stop | Out-Null
    } catch {
        throw 'npm.cmd est introuvable. Installez Node.js avant de démarrer Léa.'
    }
}

function Start-Lea {
    Assert-RequiredFiles

    $existingState = Read-LeaState
    if ($null -ne $existingState) {
        $existingSummary = Get-StateSummary -State $existingState
        if ($existingSummary.AllActive -and (Test-AllEndpointsReady)) {
            Write-Host 'Léa est déjà démarrée.'
            Write-LeaStatus -State $existingState
            return
        }

        if ($existingSummary.AllStopped) {
            Remove-LeaState -KeepLogs
        } else {
            throw "L’état de Léa est incomplet ou incohérent. Exécutez .\lea.ps1 stop avant un nouveau démarrage."
        }
    }

    foreach ($componentName in @('model', 'backend', 'frontend')) {
        $definition = $ComponentDefinitions[$componentName]
        Assert-PortFree -Port $definition.Port -ComponentLabel $definition.Label
    }

    Clear-PreviousLogs
    $state = New-LeaState
    try {
        Start-Model -State $state
        Start-Backend -State $state
        Start-Frontend -State $state
        $state.phase = 'running'
        Write-LeaState -State $state

        Write-Host ''
        Write-Host 'Léa est prête.'
        Write-Host 'Interface : http://127.0.0.1:5173'
        Write-Host 'Modèle   : actif'
        Write-Host 'Backend  : actif'
        Write-Host 'Frontend : actif'
    } catch {
        $failureMessage = $_.Exception.Message
        Write-Host "Échec du démarrage : $failureMessage" -ForegroundColor Red
        try {
            Stop-LeaFromState -State $state -KeepLogs
        } catch {
            $cleanupMessage = $_.Exception.Message
            Write-Warning "Nettoyage incomplet : $cleanupMessage"
            throw "$failureMessage Nettoyage incomplet : l’état et les journaux sont conservés."
        }

        throw $failureMessage
    }
}

function Show-LeaStatus {
    $state = Read-LeaState
    if ($null -ne $state) {
        $summary = Get-StateSummary -State $state
        if ($summary.AllStopped) {
            Remove-LeaState -KeepLogs
            $state = $null
        }
    }

    Write-LeaStatus -State $state
}

function Stop-Lea {
    $state = Read-LeaState
    if ($null -eq $state) {
        Write-Host 'Léa est déjà arrêtée.'
        return
    }

    Stop-LeaFromState -State $state
    Write-Host 'Léa est arrêtée.'
}

try {
    if ([string]::IsNullOrWhiteSpace($Action)) {
        Write-Usage
        exit 1
    }

    switch ($Action.ToLowerInvariant()) {
        'start' {
            Start-Lea
            exit 0
        }
        'status' {
            Show-LeaStatus
            exit 0
        }
        'stop' {
            Stop-Lea
            exit 0
        }
        default {
            Write-Usage
            exit 1
        }
    }
} catch {
    Write-Host "Erreur : $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}















