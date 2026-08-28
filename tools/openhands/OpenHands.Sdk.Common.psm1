Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
# Windows PowerShell 5.1 traite stderr natif comme une erreur sous Stop ; les inspect attendus abaissent localement cette preference.

# Ce bootstrap SDK reste separe de Lea et de l'ancien profil Canvas 22K.
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$script:OpenHandsSdkConfig = [ordered]@{
    ProjectRoot = $projectRoot
    # La generation smoke-v2 isole les conversations de test CamelCase conservees dans l'ancien etat SDK.
    StateRoot = Join-Path $projectRoot '.lea\openhands-sdk\smoke-v2'
    LogsRoot = Join-Path $projectRoot '.lea\openhands-sdk\smoke-v2\logs'
    StateFile = Join-Path $projectRoot '.lea\openhands-sdk\smoke-v2\bootstrap-state.json'
    WorkspaceRoot = 'L:\IA_WORKSPACE'
    WorkspaceContainerPath = '/projects'
    SmokeProjectName = 'OpenHands_SmokeTest'
    SmokeWorkingDirectory = '/projects/OpenHands_SmokeTest'
    AgentContainerName = 'lea-openhands-sdk-smoke-v2'
    AgentStateVolume = 'lea_openhands_sdk_smoke_v2'
    AgentStateContainerPath = '/home/openhands/.openhands'
    AgentImage = 'ghcr.io/openhands/agent-server@sha256:8ec6bd808b35cf50b7e5032f618ccbb33dd8e2bd80f8d130f12dafee24bab66a'
    AgentImageTag = 'ghcr.io/openhands/agent-server:1.43.1-python'
    AgentImageDigest = 'sha256:8ec6bd808b35cf50b7e5032f618ccbb33dd8e2bd80f8d130f12dafee24bab66a'
    AgentHost = '127.0.0.1'
    AgentHostPort = 18010
    AgentContainerPort = 8000
    AgentMemoryLimit = '4g'
    AgentCpuLimit = '4'
    AgentPidsLimit = 512
    LlamaExecutable = Join-Path $projectRoot 'runtime\llama.cpp\llama-server.exe'
    ModelPath = Join-Path $projectRoot 'models\development\qwen2.5-coder-14b-instruct-q5_k_m.gguf'
    ModelSizeBytes = [int64]10508873152
    ModelSha256 = '98ab25e0132e3f1e6d3554e1b64de2b5021908819b740d9c208430117e49a775'
    ChatTemplatePath = Join-Path $projectRoot 'tools\openhands\templates\qwen2.5-coder-openai-tools.jinja'
    ChatTemplateSha256 = 'a24779148fa43c5dfeec5a6a40adb2f5bbead90b01cb70a338175070144c69c6'
    LlamaHost = '127.0.0.1'
    LlamaPort = 8081
    ModelAlias = 'lea-development-openhands'
    NormalAvailableRamBytes = [int64](6GB)
    # Le profil nocturne accepte toute marge durable d'au moins 4 Gio sans OOM, pagination severe ni instabilite.
    AcceptableAvailableRamBytes = [int64](4GB)
    WarningAvailableRamBytes = [int64](4GB)
    CriticalAvailableRamBytes = [int64](4GB)
    AgentToolNames = @('terminal', 'file_editor', 'task_tracker')
    AgentToolImportModules = 'openhands.tools.terminal.definition,openhands.tools.file_editor.definition,openhands.tools.task_tracker.definition'
    TiktokenCacheRoot = Join-Path $projectRoot '.lea\openhands\tiktoken'
    TiktokenCacheFileName = '9b5ad71b2ce5302211f9c61530b329a4922fc6a4'
    TiktokenCacheSha256 = '223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7'
    SdkPython = Join-Path $projectRoot '.lea\openhands-sdk-venv\Scripts\python.exe'
    SdkRunner = Join-Path $projectRoot 'tools\openhands\run_sdk_smoke.py'
    ManagedLabel = 'com.projet-lea.openhands.managed'
    ModeLabel = 'com.projet-lea.openhands.mode'
    InstanceLabel = 'com.projet-lea.openhands.instance'
    SchemaLabel = 'com.projet-lea.openhands.schema'
}

# Retourne la configuration immuable du chemin SDK/Agent Server sans Canvas.
function Get-OpenHandsSdkConfig {
    return [pscustomobject]$script:OpenHandsSdkConfig
}

# Lit une propriete sans supposer si ConvertFrom-Json a retourne un dictionnaire ou un PSCustomObject.
function Get-OpenHandsSdkObjectValue {
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

# Ecrit une propriete d'etat en preservant le type de l'objet deserialise.
function Set-OpenHandsSdkObjectValue {
    param(
        [Parameter(Mandatory = $true)]$Object,
        [Parameter(Mandatory = $true)][string]$Name,
        $Value
    )

    if ($Object -is [System.Collections.IDictionary]) {
        $Object[$Name] = $Value
        return
    }

    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
    } else {
        $property.Value = $Value
    }
}

# Empreinte une chaine sensible ou volatile sans enregistrer sa valeur en clair dans l'etat.
function Get-OpenHandsSdkStringSha256 {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text)

    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
        return ([System.BitConverter]::ToString($sha256.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    } finally {
        $sha256.Dispose()
    }
}

# Normalise un chemin Windows pour les comparaisons de securite sans accepter de chemin relatif ambigu.
function ConvertTo-OpenHandsSdkCanonicalPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw 'Un chemin vide ne peut pas etre normalise.'
    }

    return [System.IO.Path]::GetFullPath($Path).TrimEnd([char[]]@('\', '/'))
}

# Compare deux chemins canoniques Windows sans tenir compte de la casse.
function Test-OpenHandsSdkSameCanonicalPath {
    param([string]$Left, [string]$Right)

    if ([string]::IsNullOrWhiteSpace($Left) -or [string]::IsNullOrWhiteSpace($Right)) {
        return $false
    }

    try {
        $normalLeft = ConvertTo-OpenHandsSdkCanonicalPath -Path $Left
        $normalRight = ConvertTo-OpenHandsSdkCanonicalPath -Path $Right
    } catch {
        return $false
    }

    return [string]::Equals($normalLeft, $normalRight, [System.StringComparison]::OrdinalIgnoreCase)
}

# Exige que le seul bind de projets soit la racine reelle L:\IA_WORKSPACE sans reparse point.
function Assert-OpenHandsSdkWorkspaceRoot {
    $config = Get-OpenHandsSdkConfig
    $expected = ConvertTo-OpenHandsSdkCanonicalPath -Path $config.WorkspaceRoot
    $workspace = Get-Item -LiteralPath $expected -Force -ErrorAction Stop

    if (-not $workspace.PSIsContainer) {
        throw "Le workspace OpenHands SDK n'est pas un dossier : $expected"
    }
    if (($workspace.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Le workspace OpenHands SDK ne peut pas etre un reparse point : $expected"
    }
    if (-not (Test-OpenHandsSdkSameCanonicalPath -Left $workspace.FullName -Right $expected)) {
        throw "Le workspace resolu ne correspond pas exactement a L:\IA_WORKSPACE : $($workspace.FullName)"
    }

    return $workspace.FullName
}

# Accepte seulement les deux representations Docker Desktop de la racine L:\IA_WORKSPACE.
function Test-OpenHandsSdkWorkspaceMountSource {
    param([Parameter(Mandatory = $true)][string]$Source)

    $config = Get-OpenHandsSdkConfig
    if (Test-OpenHandsSdkSameCanonicalPath -Left $Source -Right $config.WorkspaceRoot) {
        return $true
    }

    $relative = $config.WorkspaceRoot.Substring(3).Replace('\', '/').Trim('/')
    $dockerDesktopPath = "/run/desktop/mnt/host/l/$relative"
    return [string]::Equals($Source.TrimEnd('/'), $dockerDesktopPath, [System.StringComparison]::Ordinal)
}

# Cree exclusivement les journaux et l'etat ignores du bootstrap SDK.
function Ensure-OpenHandsSdkStateDirectories {
    $config = Get-OpenHandsSdkConfig
    foreach ($path in @($config.StateRoot, $config.LogsRoot)) {
        if (Test-Path -LiteralPath $path) {
            $item = Get-Item -LiteralPath $path -Force
            if (-not $item.PSIsContainer) {
                throw "Le chemin d'etat OpenHands SDK n'est pas un dossier : $path"
            }
        } else {
            New-Item -ItemType Directory -Path $path -Force | Out-Null
        }
    }
}

# Lit l'etat local et refuse d'adopter un fichier corrompu ou venant d'un autre depot.
function Read-OpenHandsSdkState {
    $config = Get-OpenHandsSdkConfig
    if (-not (Test-Path -LiteralPath $config.StateFile)) {
        return $null
    }

    try {
        $state = Get-Content -LiteralPath $config.StateFile -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop
    } catch {
        throw "L'etat OpenHands SDK est illisible ; aucun processus ou conteneur ne sera adopte : $($_.Exception.Message)"
    }

    if ([int](Get-OpenHandsSdkObjectValue -Object $state -Name 'schema_version') -ne 1) {
        throw "L'etat OpenHands SDK utilise un schema inconnu ; aucune action destructive n'est autorisee."
    }
    if (-not (Test-OpenHandsSdkSameCanonicalPath -Left ([string](Get-OpenHandsSdkObjectValue -Object $state -Name 'project_root')) -Right $config.ProjectRoot)) {
        throw "L'etat OpenHands SDK ne correspond pas a ce depot ; aucune action destructive n'est autorisee."
    }

    return $state
}

# Publie l'etat avec remplacement atomique afin qu'une interruption ne laisse pas de JSON partiel.
function Write-OpenHandsSdkStateAtomically {
    param([Parameter(Mandatory = $true)]$State)

    Ensure-OpenHandsSdkStateDirectories
    $config = Get-OpenHandsSdkConfig
    $temporary = "$($config.StateFile).$PID.$([guid]::NewGuid().ToString('N')).tmp"
    $backup = "$($config.StateFile).replace-backup"
    $encoding = New-Object System.Text.UTF8Encoding($false)
    $json = $State | ConvertTo-Json -Depth 20

    try {
        [System.IO.File]::WriteAllText($temporary, $json, $encoding)
        if (Test-Path -LiteralPath $config.StateFile) {
            if (Test-Path -LiteralPath $backup) {
                Remove-Item -LiteralPath $backup -Force -ErrorAction Stop
            }
            [System.IO.File]::Replace($temporary, $config.StateFile, $backup, $true)
        } else {
            [System.IO.File]::Move($temporary, $config.StateFile)
        }
    } finally {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
        }
        if (Test-Path -LiteralPath $backup) {
            Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
        }
    }
}

# Construit un etat neuf identifiant une seule instance SDK avant tout lancement.
function New-OpenHandsSdkState {
    param([Parameter(Mandatory = $true)][ValidateSet(22000, 20000, 18000, 16000)][int]$ContextSize)

    $config = Get-OpenHandsSdkConfig
    return [ordered]@{
        schema_version = 1
        project_root = $config.ProjectRoot
        phase = 'starting'
        instance_id = [guid]::NewGuid().ToString('D')
        created_at_utc = [datetime]::UtcNow.ToString('o')
        updated_at_utc = [datetime]::UtcNow.ToString('o')
        selected_context = $ContextSize
        image = [ordered]@{
            reference = $config.AgentImage
            tag = $config.AgentImageTag
            digest = $config.AgentImageDigest
        }
        agent_server = [ordered]@{
            container_id = $null
            name = $config.AgentContainerName
            host_url = "http://$($config.AgentHost):$($config.AgentHostPort)"
            state_volume = $config.AgentStateVolume
        }
        model = [ordered]@{
            launcher = $null
            listener = $null
            alias = $config.ModelAlias
            requested_context = $ContextSize
        }
        resources = [ordered]@{}
        attempts = @()
        result = $null
        failure = $null
    }
}

# Marque une phase et conserve une cause lisible sans ecraser les preuves accumulees.
function Set-OpenHandsSdkPhase {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)][ValidateSet('starting', 'model_ready', 'agent_ready', 'running', 'stopped', 'failed')][string]$Phase,
        [string]$Failure = $null
    )

    Set-OpenHandsSdkObjectValue -Object $State -Name 'phase' -Value $Phase
    Set-OpenHandsSdkObjectValue -Object $State -Name 'updated_at_utc' -Value ([datetime]::UtcNow.ToString('o'))
    Set-OpenHandsSdkObjectValue -Object $State -Name 'failure' -Value $Failure
}

# Execute Docker avec tableau d'arguments afin de ne jamais construire une commande shell ambigue.
function Invoke-OpenHandsSdkDocker {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $output = @(& docker @Arguments 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "Docker a echoue ($LASTEXITCODE) : $($output -join [Environment]::NewLine)"
    }
    return $output
}

# Verifie que Docker Desktop fournit bien le moteur Linux necessaire au sandbox Agent Server.
function Assert-OpenHandsSdkDockerReady {
    $version = (Invoke-OpenHandsSdkDocker -Arguments @('version', '--format', '{{.Server.Os}}/{{.Server.Arch}}|{{.Server.Version}}')).Trim()
    if ($version -notmatch '^linux/amd64\|') {
        throw "Le moteur Docker attendu linux/amd64 n'est pas disponible : $version"
    }
    return $version
}

# Verifie une fois le runtime, la taille, le hash et les options llama.cpp reellement supportees.
function Assert-OpenHandsSdkModelAndRuntime {
    $config = Get-OpenHandsSdkConfig
    foreach ($path in @($config.LlamaExecutable, $config.ModelPath, $config.ChatTemplatePath, $config.SdkPython, $config.SdkRunner)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Le composant OpenHands SDK requis est absent : $path"
        }
    }

    $model = Get-Item -LiteralPath $config.ModelPath -Force
    if ([int64]$model.Length -ne $config.ModelSizeBytes) {
        throw "La taille GGUF est incorrecte : $($model.Length) octets au lieu de $($config.ModelSizeBytes)."
    }
    $actualHash = (Get-FileHash -LiteralPath $config.ModelPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $config.ModelSha256) {
        throw "Le SHA-256 GGUF ne correspond pas au modele impose : $actualHash"
    }
    $templateHash = (Get-FileHash -LiteralPath $config.ChatTemplatePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($templateHash -ne $config.ChatTemplateSha256) {
        throw "Le SHA-256 du template Jinja OpenHands ne correspond pas a la configuration epinglee : $templateHash"
    }

    $help = @(& $config.LlamaExecutable --help 2>&1) -join "`n"
    foreach ($option in @('--host', '--port', '--alias', '--ctx-size', '--parallel', '--cache-type-k', '--cache-type-v', '--cache-ram', '--gpu-layers', '--fit', '--fit-target', '--fit-ctx', '--prio', '--mmap', '--jinja', '--no-skip-chat-parsing', '--chat-template-file')) {
        if ($help -notmatch [regex]::Escape($option)) {
            throw "Le llama-server installe ne supporte pas l'option necessaire : $option"
        }
    }

    return [pscustomobject]@{ model_sha256 = $actualHash; model_size_bytes = [int64]$model.Length; chat_template_sha256 = $templateHash }
}

# Retourne les PID TCP a l'ecoute d'un port sans jamais en deduire une propriete.
function Get-OpenHandsSdkListeningPids {
    param([Parameter(Mandatory = $true)][int]$Port)

    $netstat = Join-Path $env:SystemRoot 'System32\netstat.exe'
    $pattern = '^\s*TCP\s+\S+:' + [regex]::Escape([string]$Port) + '\s+\S+\s+LISTENING\s+(?<pid>\d+)\s*$'
    $pids = @()
    foreach ($line in @(& $netstat -ano -p tcp 2>$null)) {
        if ($line -match $pattern) {
            $pids += [int]$Matches['pid']
        }
    }
    return @($pids | Sort-Object -Unique)
}

# Refuse un port occupe car un processus trouve seulement par son port n'est jamais adopte.
function Assert-OpenHandsSdkPortFree {
    param([Parameter(Mandatory = $true)][int]$Port, [Parameter(Mandatory = $true)][string]$Label)

    $pids = @(Get-OpenHandsSdkListeningPids -Port $Port)
    if ($pids.Count -gt 0) {
        throw "Le port $Port pour $Label est deja utilise par un processus non adopte (PID $($pids -join ', '))."
    }
}

# Attend la liberation d'un port apres l'arret d'un composant dont l'identite etait deja verifiee.
function Wait-ForOpenHandsSdkPortRelease {
    param([Parameter(Mandatory = $true)][int]$Port, [Parameter(Mandatory = $true)][int]$TimeoutSeconds)

    $deadline = [datetime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([datetime]::UtcNow -lt $deadline) {
        if (@(Get-OpenHandsSdkListeningPids -Port $Port).Count -eq 0) {
            return $true
        }
        Start-Sleep -Milliseconds 250
    }
    return @(Get-OpenHandsSdkListeningPids -Port $Port).Count -eq 0
}

# Lit une ligne de commande seulement pour son empreinte de securite, jamais pour la persister en clair.
function Get-OpenHandsSdkProcessCommandLine {
    param([Parameter(Mandatory = $true)][int]$ProcessId)

    try {
        return [string](Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop).CommandLine
    } catch {
        return $null
    }
}

# Cree une empreinte de processus qui protege contre la reutilisation d'un PID.
function New-OpenHandsSdkProcessRecord {
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [Parameter(Mandatory = $true)][string]$ExpectedName,
        [Parameter(Mandatory = $true)][string]$ExpectedPath,
        [int]$Port = 0
    )

    $process = Get-Process -Id $ProcessId -ErrorAction Stop
    $path = $null
    try { $path = $process.Path } catch { $path = $null }
    $commandLine = Get-OpenHandsSdkProcessCommandLine -ProcessId $ProcessId
    if ($process.ProcessName -ine $ExpectedName) {
        throw "Le PID $ProcessId n'est pas le processus attendu : $ExpectedName"
    }
    if ([string]::IsNullOrWhiteSpace($path) -or -not (Test-OpenHandsSdkSameCanonicalPath -Left $path -Right $ExpectedPath)) {
        throw "Le chemin du PID $ProcessId ne correspond pas a l'executable attendu."
    }
    if ([string]::IsNullOrWhiteSpace($commandLine)) {
        throw "La ligne de commande du PID $ProcessId ne peut pas etre confirmee."
    }

    return [ordered]@{
        pid = [int]$process.Id
        process_name = $process.ProcessName
        executable_path = $path
        start_time_utc = $process.StartTime.ToUniversalTime().ToString('o')
        command_line_sha256 = Get-OpenHandsSdkStringSha256 -Text $commandLine
        port = [int]$Port
    }
}

# Verifie qu'un record correspond encore au meme processus avant tout arret.
function Test-OpenHandsSdkProcessRecord {
    param($Record)

    if ($null -eq $Record) {
        return [pscustomobject]@{ Exists = $false; Verified = $false; Process = $null; Reason = 'Aucun processus enregistre.' }
    }

    $processId = [int](Get-OpenHandsSdkObjectValue -Object $Record -Name 'pid')
    try {
        $process = Get-Process -Id $processId -ErrorAction Stop
    } catch {
        return [pscustomobject]@{ Exists = $false; Verified = $false; Process = $null; Reason = 'Le PID enregistre n existe plus.' }
    }

    try {
        $path = $process.Path
        $recordedTime = [datetime]::Parse([string](Get-OpenHandsSdkObjectValue -Object $Record -Name 'start_time_utc')).ToUniversalTime()
        $commandLine = Get-OpenHandsSdkProcessCommandLine -ProcessId $processId
        $verified = (
            $process.ProcessName -ieq [string](Get-OpenHandsSdkObjectValue -Object $Record -Name 'process_name') -and
            (Test-OpenHandsSdkSameCanonicalPath -Left $path -Right ([string](Get-OpenHandsSdkObjectValue -Object $Record -Name 'executable_path'))) -and
            [math]::Abs(($process.StartTime.ToUniversalTime() - $recordedTime).TotalSeconds) -lt 1 -and
            -not [string]::IsNullOrWhiteSpace($commandLine) -and
            (Get-OpenHandsSdkStringSha256 -Text $commandLine) -eq [string](Get-OpenHandsSdkObjectValue -Object $Record -Name 'command_line_sha256')
        )
    } catch {
        $verified = $false
    }

    return [pscustomobject]@{
        Exists = $true
        Verified = $verified
        Process = $process
        Reason = if ($verified) { 'Identite verifiee.' } else { 'Le nom, chemin, heure ou hash de commande ne correspondent plus.' }
    }
}

# Arrete seulement un processus verifie, puis force seulement le meme PID encore verifie s'il persiste.
function Stop-OpenHandsSdkManagedProcess {
    param([Parameter(Mandatory = $true)]$Record, [Parameter(Mandatory = $true)][string]$Label)

    $check = Test-OpenHandsSdkProcessRecord -Record $Record
    if ($check.Exists -and -not $check.Verified) {
        throw "Refus d'arreter $Label : $($check.Reason)"
    }
    if (-not $check.Exists) {
        return
    }

    Stop-Process -Id $check.Process.Id -ErrorAction Stop
    $deadline = [datetime]::UtcNow.AddSeconds(15)
    while ([datetime]::UtcNow -lt $deadline) {
        if (-not (Test-OpenHandsSdkProcessRecord -Record $Record).Exists) {
            return
        }
        Start-Sleep -Milliseconds 250
    }

    $retry = Test-OpenHandsSdkProcessRecord -Record $Record
    if ($retry.Exists -and $retry.Verified) {
        Stop-Process -Id $retry.Process.Id -Force -ErrorAction Stop
    }
}

# Attend l'API OpenAI locale et exige que l'alias dedie soit effectivement expose par llama-server.
function Wait-ForOpenHandsSdkLlamaEndpoint {
    param([Parameter(Mandatory = $true)][int]$TimeoutSeconds)

    $config = Get-OpenHandsSdkConfig
    $uri = "http://$($config.LlamaHost):$($config.LlamaPort)/v1/models"
    $deadline = [datetime]::UtcNow.AddSeconds($TimeoutSeconds)
    $lastError = $null
    while ([datetime]::UtcNow -lt $deadline) {
        try {
            $response = Invoke-RestMethod -Uri $uri -Method Get -TimeoutSec 5 -ErrorAction Stop
            $ids = @($response.data | ForEach-Object { [string]$_.id })
            if ($ids -contains $config.ModelAlias) {
                return $response
            }
            $lastError = "Alias absent : $($ids -join ', ')"
        } catch {
            $lastError = $_.Exception.Message
        }
        Start-Sleep -Milliseconds 500
    }
    throw "llama-server SDK n'est pas pret sur $uri apres $TimeoutSeconds secondes : $lastError"
}

# Mesure RAM, pagefile, modele, VRAM et WSL/Docker sans jamais arreter un processus etranger.
function Get-OpenHandsSdkResourceSnapshot {
    param(
        $ModelRecord,
        [string]$ContainerName = $null
    )

    $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
    $pagefile = @(Get-CimInstance Win32_PageFileUsage -ErrorAction SilentlyContinue | ForEach-Object {
        [ordered]@{ name = $_.Name; allocated_mb = $_.AllocatedBaseSize; used_mb = $_.CurrentUsage; peak_mb = $_.PeakUsage }
    })
    $modelMetrics = $null
    $modelCheck = Test-OpenHandsSdkProcessRecord -Record $ModelRecord
    if ($modelCheck.Exists) {
        $modelMetrics = [ordered]@{
            pid = [int]$modelCheck.Process.Id
            working_set_bytes = [int64]$modelCheck.Process.WorkingSet64
            private_bytes = [int64]$modelCheck.Process.PrivateMemorySize64
            cpu_seconds = [math]::Round($modelCheck.Process.TotalProcessorTime.TotalSeconds, 3)
        }
    }

    $gpu = $null
    try {
        $gpuLines = @(& nvidia-smi --query-gpu=memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu --format=csv,noheader,nounits 2>$null)
        if ($LASTEXITCODE -eq 0 -and $gpuLines.Count -gt 0) {
            $gpu = @($gpuLines | ForEach-Object { [string]$_ })
        }
    } catch { $gpu = $null }

    $wsl = $null
    try {
        $wslLines = @(& wsl.exe -d docker-desktop -e sh -lc "grep -E '^(MemTotal|MemAvailable|Cached|SwapTotal|SwapFree):' /proc/meminfo" 2>$null)
        if ($LASTEXITCODE -eq 0) {
            $wsl = [ordered]@{}
            foreach ($line in $wslLines) {
                if ($line -match '^(?<name>\w+):\s+(?<kb>\d+)\s+kB$') {
                    $wsl[$Matches['name']] = [int64]$Matches['kb'] * 1KB
                }
            }
        }
    } catch { $wsl = $null }

    $dockerStats = $null
    if (-not [string]::IsNullOrWhiteSpace($ContainerName)) {
        try {
            $rawStats = @(& docker container stats --no-stream --format '{{json .}}' $ContainerName 2>$null)
            if ($LASTEXITCODE -eq 0 -and $rawStats.Count -eq 1) {
                $dockerStats = $rawStats[0] | ConvertFrom-Json -ErrorAction Stop
            }
        } catch { $dockerStats = $null }
    }

    return [ordered]@{
        captured_at_utc = [datetime]::UtcNow.ToString('o')
        system_available_ram_bytes = [int64]($os.FreePhysicalMemory * 1KB)
        system_total_ram_bytes = [int64]($os.TotalVisibleMemorySize * 1KB)
        pagefile = $pagefile
        model = $modelMetrics
        gpu_csv = $gpu
        wsl = $wsl
        docker = $dockerStats
    }
}

# Prend deux mesures espacees pour confirmer une marge RAM durable a une etape donnee.
function Get-OpenHandsSdkStableResourceSamples {
    param(
        $ModelRecord,
        [string]$ContainerName = $null
    )

    $samples = @((Get-OpenHandsSdkResourceSnapshot -ModelRecord $ModelRecord -ContainerName $ContainerName))
    Start-Sleep -Seconds 5
    $samples += ,(Get-OpenHandsSdkResourceSnapshot -ModelRecord $ModelRecord -ContainerName $ContainerName)
    return $samples
}

# Classe la marge RAM selon la politique nocturne sans continuer sous le seuil critique durable de 4 Gio.
function Test-OpenHandsSdkMemoryBarrier {
    param([Parameter(Mandatory = $true)][object[]]$Samples)

    $config = Get-OpenHandsSdkConfig
    $values = @($Samples | ForEach-Object { [int64](Get-OpenHandsSdkObjectValue -Object $_ -Name 'system_available_ram_bytes') })
    if ($values.Count -eq 0) {
        throw 'La barriere memoire exige au moins un echantillon de RAM physique.'
    }
    $minimum = [int64](($values | Measure-Object -Minimum).Minimum)
    $classification = if ($minimum -ge $config.NormalAvailableRamBytes) {
        'normal'
    } elseif ($minimum -ge $config.AcceptableAvailableRamBytes) {
        'acceptable'
    } elseif ($minimum -ge $config.WarningAvailableRamBytes) {
        'warning'
    } else {
        'critical'
    }
    return [pscustomobject]@{
        Passed = $classification -ne 'critical'
        CanContinue = $classification -ne 'critical'
        RequiresUserReview = $classification -eq 'warning'
        Classification = $classification
        MinimumAvailableRamBytes = $minimum
        NormalAvailableRamBytes = $config.NormalAvailableRamBytes
        AcceptableAvailableRamBytes = $config.AcceptableAvailableRamBytes
        WarningAvailableRamBytes = $config.WarningAvailableRamBytes
        CriticalAvailableRamBytes = $config.CriticalAvailableRamBytes
    }
}

# Demarre le llama-server dedie avec un contexte explicite et enregistre son identite avant la readiness.
function Start-OpenHandsSdkLlamaServer {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)][ValidateSet(22000, 20000, 18000, 16000)][int]$ContextSize
    )

    $config = Get-OpenHandsSdkConfig
    Assert-OpenHandsSdkPortFree -Port $config.LlamaPort -Label 'llama-server OpenHands SDK'
    Ensure-OpenHandsSdkStateDirectories
    $stdin = Join-Path $config.StateRoot 'llama.stdin.empty'
    [System.IO.File]::WriteAllText($stdin, [string]::Empty)
    $stamp = [datetime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    $stdout = Join-Path $config.LogsRoot "llama-$ContextSize-$stamp.stdout.log"
    $stderr = Join-Path $config.LogsRoot "llama-$ContextSize-$stamp.stderr.log"
    $arguments = @(
        '-m', $config.ModelPath,
        '--host', $config.LlamaHost,
        '--port', [string]$config.LlamaPort,
        '--alias', $config.ModelAlias,
        '--ctx-size', [string]$ContextSize,
        '--parallel', '1',
        '--cache-type-k', 'q4_0',
        '--cache-type-v', 'q4_0',
        '--cache-ram', '0',
        '--gpu-layers', 'auto',
        '--fit', 'on',
        '--fit-target', '1024',
        '--fit-ctx', [string]$ContextSize,
        '--prio', '-1',
        '--mmap',
        '--threads', '8',
        '--batch-size', '512',
        '--ubatch-size', '128',
        '--jinja',
        '--no-skip-chat-parsing',
        '--chat-template-file', $config.ChatTemplatePath
    )

    $process = $null
    $record = $null
    try {
        $process = Start-Process -FilePath $config.LlamaExecutable -ArgumentList $arguments -WorkingDirectory $config.ProjectRoot -PassThru -WindowStyle Hidden -RedirectStandardInput $stdin -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        $record = New-OpenHandsSdkProcessRecord -ProcessId $process.Id -ExpectedName 'llama-server' -ExpectedPath $config.LlamaExecutable
        $model = Get-OpenHandsSdkObjectValue -Object $State -Name 'model'
        Set-OpenHandsSdkObjectValue -Object $model -Name 'launcher' -Value $record
        Set-OpenHandsSdkObjectValue -Object $model -Name 'listener' -Value $null
        Set-OpenHandsSdkObjectValue -Object $model -Name 'requested_context' -Value $ContextSize
        Set-OpenHandsSdkObjectValue -Object $State -Name 'selected_context' -Value $ContextSize
        Write-OpenHandsSdkStateAtomically -State $State

        [void](Wait-ForOpenHandsSdkLlamaEndpoint -TimeoutSeconds 240)
        $listeners = @(Get-OpenHandsSdkListeningPids -Port $config.LlamaPort)
        if ($listeners.Count -ne 1 -or $listeners[0] -ne $process.Id) {
            throw "llama-server SDK doit etre l'unique PID a l'ecoute sur $($config.LlamaPort)."
        }
        $listener = New-OpenHandsSdkProcessRecord -ProcessId $listeners[0] -ExpectedName 'llama-server' -ExpectedPath $config.LlamaExecutable -Port $config.LlamaPort
        Set-OpenHandsSdkObjectValue -Object $model -Name 'listener' -Value $listener
        Set-OpenHandsSdkPhase -State $State -Phase 'model_ready'
        Write-OpenHandsSdkStateAtomically -State $State
        return $State
    } catch {
        if ($null -ne $record) {
            try { Stop-OpenHandsSdkManagedProcess -Record $record -Label 'llama-server lance pendant cette tentative' } catch { Write-Warning $_.Exception.Message }
        }
        Set-OpenHandsSdkPhase -State $State -Phase 'failed' -Failure $_.Exception.Message
        Write-OpenHandsSdkStateAtomically -State $State
        throw
    }
}

# Arrete uniquement les PID llama-server qui correspondent encore a l'etat signe localement.
function Stop-OpenHandsSdkLlamaServer {
    param([Parameter(Mandatory = $true)]$State)

    $config = Get-OpenHandsSdkConfig
    $model = Get-OpenHandsSdkObjectValue -Object $State -Name 'model'
    $listener = Get-OpenHandsSdkObjectValue -Object $model -Name 'listener'
    $launcher = Get-OpenHandsSdkObjectValue -Object $model -Name 'launcher'
    if ($null -ne $listener -and [int](Get-OpenHandsSdkObjectValue -Object $listener -Name 'pid') -ne [int](Get-OpenHandsSdkObjectValue -Object $launcher -Name 'pid')) {
        Stop-OpenHandsSdkManagedProcess -Record $listener -Label 'ecouteur llama-server SDK'
    }
    if ($null -ne $launcher) {
        Stop-OpenHandsSdkManagedProcess -Record $launcher -Label 'llama-server SDK'
    }
    if (-not (Wait-ForOpenHandsSdkPortRelease -Port $config.LlamaPort -TimeoutSeconds 30)) {
        throw "Le port $($config.LlamaPort) reste occupe ; aucun PID inconnu ne sera arrete."
    }
}

# Inspecte un conteneur Docker sans le demarrer ni le modifier.
function Get-OpenHandsSdkContainerInspection {
    param([Parameter(Mandatory = $true)][string]$Identifier)

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # Un conteneur absent est un resultat normal pour le premier demarrage et ne doit pas interrompre le contrat.
        $ErrorActionPreference = 'Continue'
        $output = @(& docker container inspect $Identifier 2>$null)
        $inspectExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($inspectExitCode -ne 0) {
        return $null
    }
    $items = @((($output -join "`n") | ConvertFrom-Json -ErrorAction Stop))
    if ($items.Count -ne 1) {
        throw "Docker a retourne un nombre ambigu de conteneurs pour $Identifier."
    }
    return $items[0]
}

# Verifie ou telecharge exclusivement l'image Agent Server epinglee par digest.
function Ensure-OpenHandsSdkAgentImage {
    $config = Get-OpenHandsSdkConfig
    $image = $null
    try {
        $raw = Invoke-OpenHandsSdkDocker -Arguments @('image', 'inspect', $config.AgentImage)
        $image = ($raw -join "`n") | ConvertFrom-Json -ErrorAction Stop
    } catch {
        Invoke-OpenHandsSdkDocker -Arguments @('pull', $config.AgentImage) | Out-Null
        $raw = Invoke-OpenHandsSdkDocker -Arguments @('image', 'inspect', $config.AgentImage)
        $image = ($raw -join "`n") | ConvertFrom-Json -ErrorAction Stop
    }

    $repoDigests = @($image.RepoDigests | ForEach-Object { [string]$_ })
    if (-not ($repoDigests | Where-Object { $_ -match [regex]::Escape($config.AgentImageDigest) })) {
        throw "L'image Agent Server locale ne porte pas le digest attendu : $($config.AgentImageDigest)"
    }
    return $image
}

# Cree ou valide le seul volume d'etat dedie au SDK, separe du volume Canvas historique.
function Ensure-OpenHandsSdkStateVolume {
    $config = Get-OpenHandsSdkConfig
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # Le volume SDK peut legitimement etre absent avant la toute premiere tentative.
        $ErrorActionPreference = 'Continue'
        $output = @(& docker volume inspect $config.AgentStateVolume 2>$null)
        $inspectExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($inspectExitCode -ne 0) {
        Invoke-OpenHandsSdkDocker -Arguments @(
            'volume', 'create',
            '--label', "$($config.ManagedLabel)=true",
            '--label', "$($config.ModeLabel)=sdk-agent-server",
            '--label', "$($config.SchemaLabel)=1",
            $config.AgentStateVolume
        ) | Out-Null
        $output = Invoke-OpenHandsSdkDocker -Arguments @('volume', 'inspect', $config.AgentStateVolume)
    }
    $volume = @((($output -join "`n") | ConvertFrom-Json -ErrorAction Stop))[0]
    $labels = Get-OpenHandsSdkObjectValue -Object $volume -Name 'Labels'
    if ([string](Get-OpenHandsSdkObjectValue -Object $labels -Name $config.ManagedLabel) -ne 'true' -or [string](Get-OpenHandsSdkObjectValue -Object $labels -Name $config.ModeLabel) -ne 'sdk-agent-server') {
        throw "Le volume $($config.AgentStateVolume) existe mais ne respecte pas le contrat SDK ; il ne sera pas adopte."
    }
    return $volume
}

# Copie une fois le vocabulaire tiktoken verifie dans le volume sans monter un dossier hote supplementaire.
function Initialize-OpenHandsSdkTiktokenCache {
    param([Parameter(Mandatory = $true)]$State)

    $config = Get-OpenHandsSdkConfig
    $cacheFile = Join-Path $config.TiktokenCacheRoot $config.TiktokenCacheFileName
    if (-not (Test-Path -LiteralPath $cacheFile -PathType Leaf)) {
        throw "Le cache tiktoken local manque : $cacheFile"
    }
    if ((Get-FileHash -LiteralPath $cacheFile -Algorithm SHA256).Hash.ToLowerInvariant() -ne $config.TiktokenCacheSha256) {
        throw 'Le cache tiktoken local ne correspond pas au hash officiel attendu.'
    }

    Ensure-OpenHandsSdkStateVolume | Out-Null
    $seedName = "lea-openhands-sdk-tiktoken-$([guid]::NewGuid().ToString('N'))"
    $seedId = $null
    try {
        $seedId = ([string](Invoke-OpenHandsSdkDocker -Arguments @(
            'container', 'create',
            '--name', $seedName,
            '--label', "$($config.ManagedLabel)=true",
            '--label', "$($config.ModeLabel)=sdk-tiktoken-seed",
            '--label', "$($config.InstanceLabel)=$([string](Get-OpenHandsSdkObjectValue -Object $State -Name 'instance_id'))",
            '--label', "$($config.SchemaLabel)=1",
            '--user', '0:0',
            '--mount', "type=volume,src=$($config.AgentStateVolume),dst=$($config.AgentStateContainerPath)",
            '--entrypoint', '/bin/sh',
            $config.AgentImage,
            '-lc', 'mkdir -p /home/openhands/.openhands/tiktoken && while true; do sleep 30; done'
        ) | Select-Object -Last 1)).Trim()
        if ($seedId -notmatch '^[0-9a-f]{64}$') {
            throw "Docker n'a pas retourne un ID de conteneur seed valide : $seedId"
        }
        Invoke-OpenHandsSdkDocker -Arguments @('container', 'start', $seedId) | Out-Null
        Start-Sleep -Milliseconds 500
        $destination = "$seedId`:/home/openhands/.openhands/tiktoken/$($config.TiktokenCacheFileName)"
        $copyOutput = @(& docker container cp $cacheFile $destination 2>&1)
        if ($LASTEXITCODE -ne 0) {
            throw "La copie du cache tiktoken dans le volume a echoue : $($copyOutput -join [Environment]::NewLine)"
        }
        # docker cp ecrit depuis l'hote en root ; le serveur tourne en utilisateur openhands et doit pouvoir creer ses profils dans ce volume.
        $hashOutput = Invoke-OpenHandsSdkDocker -Arguments @('container', 'exec', $seedId, 'sh', '-lc', "chown -R openhands:openhands /home/openhands/.openhands && sha256sum /home/openhands/.openhands/tiktoken/$($config.TiktokenCacheFileName)")
        if (($hashOutput -join "`n") -notmatch [regex]::Escape($config.TiktokenCacheSha256)) {
            throw 'Le hash du cache tiktoken dans le volume ne correspond pas au fichier verifie.'
        }
    } finally {
        if ($null -ne $seedId) {
            $seed = Get-OpenHandsSdkContainerInspection -Identifier $seedId
            if ($null -ne $seed) {
                $labels = Get-OpenHandsSdkObjectValue -Object (Get-OpenHandsSdkObjectValue -Object $seed -Name 'Config') -Name 'Labels'
                if ([string](Get-OpenHandsSdkObjectValue -Object $labels -Name $config.ManagedLabel) -eq 'true' -and [string](Get-OpenHandsSdkObjectValue -Object $labels -Name $config.ModeLabel) -eq 'sdk-tiktoken-seed') {
                    if ([bool](Get-OpenHandsSdkObjectValue -Object (Get-OpenHandsSdkObjectValue -Object $seed -Name 'State') -Name 'Running')) {
                        Invoke-OpenHandsSdkDocker -Arguments @('container', 'stop', '--time', '5', $seedId) | Out-Null
                    }
                    Invoke-OpenHandsSdkDocker -Arguments @('container', 'rm', $seedId) | Out-Null
                } else {
                    throw 'Le conteneur temporaire de cache ne peut pas etre confirme ; il est conserve sans suppression.'
                }
            }
        }
    }
}

# Teste le contrat de securite et d'isolation du conteneur Agent Server minimal.
function Test-OpenHandsSdkAgentContainer {
    param([Parameter(Mandatory = $true)]$Container, [Parameter(Mandatory = $true)]$State)

    $config = Get-OpenHandsSdkConfig
    $containerConfig = Get-OpenHandsSdkObjectValue -Object $Container -Name 'Config'
    $hostConfig = Get-OpenHandsSdkObjectValue -Object $Container -Name 'HostConfig'
    $stateData = Get-OpenHandsSdkObjectValue -Object $Container -Name 'State'
    $labels = Get-OpenHandsSdkObjectValue -Object $containerConfig -Name 'Labels'
    $reasons = New-Object 'System.Collections.Generic.List[string]'
    if ([string](Get-OpenHandsSdkObjectValue -Object $containerConfig -Name 'Image') -ne $config.AgentImage) { $reasons.Add('image differente') }
    if ([string](Get-OpenHandsSdkObjectValue -Object $labels -Name $config.ManagedLabel) -ne 'true') { $reasons.Add('label managed absent') }
    if ([string](Get-OpenHandsSdkObjectValue -Object $labels -Name $config.ModeLabel) -ne 'sdk-agent-server') { $reasons.Add('mode SDK absent') }
    if ([string](Get-OpenHandsSdkObjectValue -Object $labels -Name $config.InstanceLabel) -ne [string](Get-OpenHandsSdkObjectValue -Object $State -Name 'instance_id')) { $reasons.Add('instance differente') }
    if ([bool](Get-OpenHandsSdkObjectValue -Object $hostConfig -Name 'Privileged')) { $reasons.Add('conteneur privilegie') }
    if ([string](Get-OpenHandsSdkObjectValue -Object $hostConfig -Name 'NetworkMode') -eq 'host') { $reasons.Add('reseau host interdit') }
    if ([int64](Get-OpenHandsSdkObjectValue -Object $hostConfig -Name 'Memory') -ne [int64](4GB)) { $reasons.Add('limite RAM Docker inattendue') }

    $mounts = @((Get-OpenHandsSdkObjectValue -Object $Container -Name 'Mounts'))
    if ($mounts.Count -ne 2) { $reasons.Add('nombre de mounts different de deux') }
    $workspaceMount = @($mounts | Where-Object { [string](Get-OpenHandsSdkObjectValue -Object $_ -Name 'Destination') -eq $config.WorkspaceContainerPath })
    $stateMount = @($mounts | Where-Object { [string](Get-OpenHandsSdkObjectValue -Object $_ -Name 'Destination') -eq $config.AgentStateContainerPath })
    if ($workspaceMount.Count -ne 1 -or -not (Test-OpenHandsSdkWorkspaceMountSource -Source ([string](Get-OpenHandsSdkObjectValue -Object $workspaceMount[0] -Name 'Source')))) { $reasons.Add('bind workspace non conforme') }
    if ($stateMount.Count -ne 1 -or [string](Get-OpenHandsSdkObjectValue -Object $stateMount[0] -Name 'Name') -ne $config.AgentStateVolume) { $reasons.Add('volume etat non conforme') }
    foreach ($mount in $mounts) {
        if ([string](Get-OpenHandsSdkObjectValue -Object $mount -Name 'Source') -match '(?i)Projet_Lea|docker\.sock') { $reasons.Add('mount interdit detecte') }
    }

    $portBindings = Get-OpenHandsSdkObjectValue -Object $hostConfig -Name 'PortBindings'
    $bindings = @((Get-OpenHandsSdkObjectValue -Object $portBindings -Name "$($config.AgentContainerPort)/tcp"))
    if ($bindings.Count -ne 1 -or [string](Get-OpenHandsSdkObjectValue -Object $bindings[0] -Name 'HostIp') -ne $config.AgentHost -or [int](Get-OpenHandsSdkObjectValue -Object $bindings[0] -Name 'HostPort') -ne $config.AgentHostPort) { $reasons.Add('publication loopback non conforme') }

    $commandText = ((@([string](Get-OpenHandsSdkObjectValue -Object $Container -Name 'Path')) + @((Get-OpenHandsSdkObjectValue -Object $Container -Name 'Args') | ForEach-Object { [string]$_ })) -join ' ')
    if ($commandText -notmatch 'openhands-agent-server' -or $commandText -match 'agent-canvas') { $reasons.Add('entrypoint Agent Server minimal non confirme') }
    if ($commandText -notmatch [regex]::Escape($config.AgentToolImportModules)) { $reasons.Add('prechargement des outils SDK absent') }
    $environment = @((Get-OpenHandsSdkObjectValue -Object $containerConfig -Name 'Env'))
    foreach ($requiredEnvironment in @('OH_ENABLE_VNC=0', 'OH_ENABLE_VSCODE=0', 'OH_PRELOAD_TOOLS=0', 'OH_WEBHOOKS=[]', 'LITELLM_LOCAL_MODEL_COST_MAP=True', 'CUSTOM_TIKTOKEN_CACHE_DIR=/home/openhands/.openhands/tiktoken')) {
        if ($environment -notcontains $requiredEnvironment) { $reasons.Add("variable absente: $requiredEnvironment") }
    }

    return [pscustomobject]@{
        Exists = $true
        Verified = $reasons.Count -eq 0
        Running = [bool](Get-OpenHandsSdkObjectValue -Object $stateData -Name 'Running')
        Container = $Container
        Reason = if ($reasons.Count -eq 0) { 'Contrat Agent Server verifie.' } else { $reasons -join '; ' }
    }
}

# Attend seulement l'endpoint Agent Server publie sur loopback, sans interface Canvas.
function Wait-ForOpenHandsSdkAgentServer {
    param([Parameter(Mandatory = $true)][int]$TimeoutSeconds)

    $config = Get-OpenHandsSdkConfig
    $uri = "http://$($config.AgentHost):$($config.AgentHostPort)/health"
    $deadline = [datetime]::UtcNow.AddSeconds($TimeoutSeconds)
    $lastError = $null
    while ([datetime]::UtcNow -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
                return $uri
            }
        } catch { $lastError = $_.Exception.Message }
        Start-Sleep -Milliseconds 500
    }
    throw "L'Agent Server SDK ne repond pas sur $uri apres $TimeoutSeconds secondes : $lastError"
}

# Lit l'endpoint officiel Agent Server avant toute conversation afin d'exposer les noms reels du registre distant.
function Get-OpenHandsSdkAgentServerToolNames {
    param()

    $config = Get-OpenHandsSdkConfig
    $uri = "http://$($config.AgentHost):$($config.AgentHostPort)/api/tools/"
    $response = Invoke-RestMethod -Uri $uri -Method Get -TimeoutSec 15 -ErrorAction Stop
    $items = @()
    if ($response -is [System.Array]) {
        $items = @($response)
    } else {
        foreach ($propertyName in @('tools', 'data', 'items')) {
            $candidate = Get-OpenHandsSdkObjectValue -Object $response -Name $propertyName
            if ($null -ne $candidate) {
                $items = @($candidate)
                break
            }
        }
    }
    if ($items.Count -eq 0) {
        throw "L'endpoint officiel $uri n'a retourne aucun outil exploitable."
    }

    $names = @(
        $items |
            ForEach-Object {
                if ($_ -is [string]) {
                    [string]$_
                } else {
                    $name = Get-OpenHandsSdkObjectValue -Object $_ -Name 'name'
                    if ($null -eq $name) {
                        $name = Get-OpenHandsSdkObjectValue -Object $_ -Name 'tool_name'
                    }
                    if ($null -ne $name) { [string]$name }
                }
            } |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
            Sort-Object -Unique
    )
    return [pscustomobject]@{ Uri = $uri; Names = $names }
}

# Refuse le run avant conversation si l'Agent Server ne resout pas les trois outils SDK officiels attendus.
function Assert-OpenHandsSdkAgentServerTools {
    param()

    $config = Get-OpenHandsSdkConfig
    $available = Get-OpenHandsSdkAgentServerToolNames
    $missing = @($config.AgentToolNames | Where-Object { $available.Names -notcontains $_ })
    if ($missing.Count -gt 0) {
        throw "Le registre Agent Server ne contient pas les outils SDK requis : $($missing -join ', '). Disponibles : $($available.Names -join ', ')."
    }
    return $available
}

# Confirme depuis le vrai conteneur que Docker Desktop atteint exclusivement le llama-server Windows local.
function Test-OpenHandsSdkContainerLlamaEndpoint {
    param([Parameter(Mandatory = $true)]$State)

    $config = Get-OpenHandsSdkConfig
    $agent = Get-OpenHandsSdkObjectValue -Object $State -Name 'agent_server'
    $containerId = [string](Get-OpenHandsSdkObjectValue -Object $agent -Name 'container_id')
    $container = Get-OpenHandsSdkContainerInspection -Identifier $containerId
    if ($null -eq $container) { throw 'Le conteneur Agent Server enregistre est absent.' }
    $contract = Test-OpenHandsSdkAgentContainer -Container $container -State $State
    if (-not $contract.Verified -or -not $contract.Running) { throw "Le conteneur Agent Server n'est pas pret : $($contract.Reason)" }
    $python = "import json, urllib.request; data=json.load(urllib.request.urlopen('http://host.docker.internal:$($config.LlamaPort)/v1/models', timeout=10)); assert any(item.get('id') == '$($config.ModelAlias)' for item in data.get('data', [])); print('$($config.ModelAlias)')"
    $result = Invoke-OpenHandsSdkDocker -Arguments @('container', 'exec', $containerId, 'python', '-c', $python)
    if (($result -join "`n").Trim() -ne $config.ModelAlias) {
        throw 'Le test depuis Agent Server ne confirme pas l alias Qwen local.'
    }
    return $true
}

# Demarre ou reprend seulement le conteneur SDK dont le contrat de securite est strictement verifie.
function Start-OpenHandsSdkAgentServer {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)][ValidateSet(22000, 20000, 18000, 16000)][int]$ContextSize
    )

    $config = Get-OpenHandsSdkConfig
    $startedForThisInvocation = $false
    try {
        Assert-OpenHandsSdkPortFree -Port $config.AgentHostPort -Label 'Agent Server OpenHands SDK'
        Ensure-OpenHandsSdkAgentImage | Out-Null
        Initialize-OpenHandsSdkTiktokenCache -State $State
        $existing = Get-OpenHandsSdkContainerInspection -Identifier $config.AgentContainerName
        if ($null -ne $existing) {
        $contract = Test-OpenHandsSdkAgentContainer -Container $existing -State $State
        if (-not $contract.Verified) { throw "Le conteneur $($config.AgentContainerName) existe mais n'est pas adopte : $($contract.Reason)" }
        if ($contract.Running) { throw 'Double demarrage Agent Server SDK refuse.' }
            Invoke-OpenHandsSdkDocker -Arguments @('container', 'start', [string](Get-OpenHandsSdkObjectValue -Object $existing -Name 'Id')) | Out-Null
            $startedForThisInvocation = $true
        } else {
        $workspace = Assert-OpenHandsSdkWorkspaceRoot
        $agent = Get-OpenHandsSdkObjectValue -Object $State -Name 'agent_server'
        $runArguments = @(
            'container', 'run', '--detach',
            '--name', $config.AgentContainerName,
            '--label', "$($config.ManagedLabel)=true",
            '--label', "$($config.ModeLabel)=sdk-agent-server",
            '--label', "$($config.InstanceLabel)=$([string](Get-OpenHandsSdkObjectValue -Object $State -Name 'instance_id'))",
            '--label', "$($config.SchemaLabel)=1",
            '--publish', "$($config.AgentHost):$($config.AgentHostPort):$($config.AgentContainerPort)",
            '--mount', "type=bind,src=$workspace,dst=$($config.WorkspaceContainerPath)",
            '--mount', "type=volume,src=$($config.AgentStateVolume),dst=$($config.AgentStateContainerPath)",
            '--workdir', $config.SmokeWorkingDirectory,
            '--memory', $config.AgentMemoryLimit,
            '--memory-swap', $config.AgentMemoryLimit,
            '--cpus', $config.AgentCpuLimit,
            '--pids-limit', [string]$config.AgentPidsLimit,
            '--security-opt', 'no-new-privileges:true',
            '--env', 'OH_ENABLE_VNC=0',
            '--env', 'OH_ENABLE_VSCODE=0',
            '--env', 'OH_PRELOAD_TOOLS=0',
            '--env', 'OH_WEBHOOKS=[]',
            '--env', 'LITELLM_LOCAL_MODEL_COST_MAP=True',
            '--env', 'CUSTOM_TIKTOKEN_CACHE_DIR=/home/openhands/.openhands/tiktoken',
            '--env', 'OPENHANDS_SUPPRESS_BANNER=1'
        )
        if ($ContextSize -eq 16000) {
            $runArguments += @('--env', 'ALLOW_SHORT_CONTEXT_WINDOWS=true')
        }
        $runArguments += @(
            $config.AgentImage,
            '--host', '0.0.0.0',
            '--port', [string]$config.AgentContainerPort,
            '--import-modules', $config.AgentToolImportModules
        )
        $containerId = ([string](Invoke-OpenHandsSdkDocker -Arguments $runArguments | Select-Object -Last 1)).Trim()
        if ($containerId -notmatch '^[0-9a-f]{64}$') { throw "Docker n'a pas retourne un ID Agent Server valide : $containerId" }
            Set-OpenHandsSdkObjectValue -Object $agent -Name 'container_id' -Value $containerId
            Write-OpenHandsSdkStateAtomically -State $State
            $startedForThisInvocation = $true
        }

        [void](Wait-ForOpenHandsSdkAgentServer -TimeoutSeconds 120)
        $agent = Get-OpenHandsSdkObjectValue -Object $State -Name 'agent_server'
        $container = Get-OpenHandsSdkContainerInspection -Identifier ([string](Get-OpenHandsSdkObjectValue -Object $agent -Name 'container_id'))
        $contract = Test-OpenHandsSdkAgentContainer -Container $container -State $State
        if (-not $contract.Verified -or -not $contract.Running) { throw "Le conteneur Agent Server cree ne respecte pas le contrat : $($contract.Reason)" }
        $availableTools = Assert-OpenHandsSdkAgentServerTools
        Set-OpenHandsSdkObjectValue -Object $agent -Name 'available_tools' -Value $availableTools.Names
        Write-OpenHandsSdkStateAtomically -State $State
        Test-OpenHandsSdkContainerLlamaEndpoint -State $State | Out-Null
        Set-OpenHandsSdkPhase -State $State -Phase 'agent_ready'
        Write-OpenHandsSdkStateAtomically -State $State
        return $State
    } catch {
        if ($startedForThisInvocation) {
            # Le lancement a cree ou repris ce conteneur connu : le stopper evite un orphelin avant de propager l'erreur.
            try { Stop-OpenHandsSdkAgentServer -State $State } catch { Write-Warning $_.Exception.Message }
        }
        throw
    }
}

# Arrete seulement le conteneur SDK exact puis attend la liberation du port loopback dedie.
function Stop-OpenHandsSdkAgentServer {
    param([Parameter(Mandatory = $true)]$State)

    $config = Get-OpenHandsSdkConfig
    $agent = Get-OpenHandsSdkObjectValue -Object $State -Name 'agent_server'
    $identifier = [string](Get-OpenHandsSdkObjectValue -Object $agent -Name 'container_id')
    if ([string]::IsNullOrWhiteSpace($identifier)) { return }
    $container = Get-OpenHandsSdkContainerInspection -Identifier $identifier
    if ($null -eq $container) { return }
    $contract = Test-OpenHandsSdkAgentContainer -Container $container -State $State
    if (-not $contract.Verified) { throw "Refus d'arreter Agent Server SDK : $($contract.Reason)" }
    if ($contract.Running) {
        Invoke-OpenHandsSdkDocker -Arguments @('container', 'stop', '--time', '30', $identifier) | Out-Null
    }
    if (-not (Wait-ForOpenHandsSdkPortRelease -Port $config.AgentHostPort -TimeoutSeconds 40)) {
        throw "Le port $($config.AgentHostPort) reste occupe ; aucun PID inconnu ne sera arrete."
    }
}

# Effectue un vrai appel OpenAI-compatible avec tools avant le run afin de confirmer le tool calling natif de Qwen.
function Invoke-OpenHandsSdkNativeToolProbe {
    $config = Get-OpenHandsSdkConfig
    $body = [ordered]@{
        model = $config.ModelAlias
        temperature = 0
        max_tokens = 128
        messages = @(
            [ordered]@{ role = 'system'; content = 'You are Qwen, created by Alibaba Cloud. You are a helpful assistant.' },
            [ordered]@{ role = 'user'; content = 'Call the record_smoke_probe function with value ok. Return no prose before the tool call.' }
        )
        tools = @([ordered]@{
            type = 'function'
            function = [ordered]@{
                name = 'record_smoke_probe'
                description = 'Record the fixed smoke probe value.'
                parameters = [ordered]@{
                    type = 'object'
                    properties = [ordered]@{ value = [ordered]@{ type = 'string' } }
                    required = @('value')
                    additionalProperties = $false
                }
            }
        })
        # llama.cpp b10355 documente tool_choice comme une chaine ; un seul outil et l'instruction imperative rendent ce probe deterministe.
        tool_choice = 'auto'
    } | ConvertTo-Json -Depth 20
    $uri = "http://$($config.LlamaHost):$($config.LlamaPort)/v1/chat/completions"
    $response = Invoke-RestMethod -Uri $uri -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 180 -ErrorAction Stop
    $choices = @((Get-OpenHandsSdkObjectValue -Object $response -Name 'choices'))
    if ($choices.Count -ne 1) {
        throw "Le probe OpenAI-compatible a retourne $($choices.Count) choix au lieu d'un seul."
    }
    $choice = $choices[0]
    $message = Get-OpenHandsSdkObjectValue -Object $choice -Name 'message'
    if ($null -eq $message) {
        throw 'Le probe OpenAI-compatible ne contient pas de message assistant.'
    }
    $finishReason = [string](Get-OpenHandsSdkObjectValue -Object $choice -Name 'finish_reason')
    $responseModel = [string](Get-OpenHandsSdkObjectValue -Object $response -Name 'model')
    $content = [string](Get-OpenHandsSdkObjectValue -Object $message -Name 'content')
    $callsValue = Get-OpenHandsSdkObjectValue -Object $message -Name 'tool_calls'
    # Encapsule aussi la branche a un seul appel : PowerShell decompose sinon le tableau et masque .Count sous StrictMode.
    $calls = @(
        if ($null -ne $callsValue) {
            @($callsValue | Where-Object { $null -ne $_ })
        }
    )
    $diagnostic = "finish_reason=$finishReason; model=$responseModel; tool_call_count=$($calls.Count); content_length=$($content.Length); content_sha256=$(Get-OpenHandsSdkStringSha256 -Text $content)"
    if ($responseModel -ne $config.ModelAlias -or $finishReason -ne 'tool_calls' -or $calls.Count -ne 1) {
        throw "Le probe OpenAI-compatible n'a pas produit le tool call natif attendu ($diagnostic)."
    }
    if ($content -match '<\s*/?(?:tool|tools|function)[^>]*>') {
        throw "Le probe a recu un marquage d'outil non parse dans content ($diagnostic)."
    }
    $call = $calls[0]
    $function = Get-OpenHandsSdkObjectValue -Object $call -Name 'function'
    $callType = [string](Get-OpenHandsSdkObjectValue -Object $call -Name 'type')
    $callName = [string](Get-OpenHandsSdkObjectValue -Object $function -Name 'name')
    $arguments = Get-OpenHandsSdkObjectValue -Object $function -Name 'arguments'
    if ($callType -ne 'function' -or $callName -ne 'record_smoke_probe' -or $null -eq $arguments) {
        throw "Le probe a retourne un tool call de forme inattendue ($diagnostic)."
    }
    try {
        $argumentObject = if ($arguments -is [string]) {
            $arguments | ConvertFrom-Json -ErrorAction Stop
        } else {
            $arguments
        }
        $argumentValue = [string](Get-OpenHandsSdkObjectValue -Object $argumentObject -Name 'value')
    } catch {
        throw "Le probe a retourne des arguments d'outil invalides ($diagnostic)."
    }
    if ($argumentValue -ne 'ok') {
        throw "Le probe a retourne une valeur d'argument inattendue ($diagnostic)."
    }
    return [ordered]@{
        model = $responseModel
        tool_call_name = 'record_smoke_probe'
        finish_reason = $finishReason
        arguments_kind = if ($arguments -is [string]) { 'json_string' } else { 'json_object' }
        usage = Get-OpenHandsSdkObjectValue -Object $response -Name 'usage'
    }
}

# Retourne un statut lecture seule du chemin SDK, y compris les ressources observables et le contrat de conteneur.
function Get-OpenHandsSdkStatus {
    $config = Get-OpenHandsSdkConfig
    $state = $null
    $stateError = $null
    try { $state = Read-OpenHandsSdkState } catch { $stateError = $_.Exception.Message }
    $containerCheck = $null
    $modelCheck = $null
    if ($null -ne $state) {
        $agent = Get-OpenHandsSdkObjectValue -Object $state -Name 'agent_server'
        $identifier = [string](Get-OpenHandsSdkObjectValue -Object $agent -Name 'container_id')
        if (-not [string]::IsNullOrWhiteSpace($identifier)) {
            $container = Get-OpenHandsSdkContainerInspection -Identifier $identifier
            if ($null -ne $container) { $containerCheck = Test-OpenHandsSdkAgentContainer -Container $container -State $state }
        }
        $modelCheck = Test-OpenHandsSdkProcessRecord -Record (Get-OpenHandsSdkObjectValue -Object (Get-OpenHandsSdkObjectValue -Object $state -Name 'model') -Name 'listener')
    }
    $resources = $null
    try {
        $record = if ($null -eq $state) { $null } else { Get-OpenHandsSdkObjectValue -Object (Get-OpenHandsSdkObjectValue -Object $state -Name 'model') -Name 'listener' }
        $resources = Get-OpenHandsSdkResourceSnapshot -ModelRecord $record -ContainerName $config.AgentContainerName
    } catch { $resources = $null }
    return [pscustomobject]@{
        state = $state
        state_error = $stateError
        agent_server = $containerCheck
        model = $modelCheck
        agent_url = "http://$($config.AgentHost):$($config.AgentHostPort)"
        model_url = "http://$($config.LlamaHost):$($config.LlamaPort)/v1/models"
        workspace = $config.WorkspaceRoot
        resources = $resources
    }
}

Export-ModuleMember -Function @(
    'Get-OpenHandsSdkConfig',
    'Get-OpenHandsSdkObjectValue',
    'Set-OpenHandsSdkObjectValue',
    'Assert-OpenHandsSdkWorkspaceRoot',
    'Ensure-OpenHandsSdkStateDirectories',
    'Read-OpenHandsSdkState',
    'Write-OpenHandsSdkStateAtomically',
    'New-OpenHandsSdkState',
    'Set-OpenHandsSdkPhase',
    'Assert-OpenHandsSdkDockerReady',
    'Assert-OpenHandsSdkModelAndRuntime',
    'Get-OpenHandsSdkResourceSnapshot',
    'Get-OpenHandsSdkStableResourceSamples',
    'Test-OpenHandsSdkMemoryBarrier',
    'Start-OpenHandsSdkLlamaServer',
    'Stop-OpenHandsSdkLlamaServer',
    'Get-OpenHandsSdkAgentServerToolNames',
    'Assert-OpenHandsSdkAgentServerTools',
    'Start-OpenHandsSdkAgentServer',
    'Stop-OpenHandsSdkAgentServer',
    'Invoke-OpenHandsSdkNativeToolProbe',
    'Get-OpenHandsSdkStatus'
)
