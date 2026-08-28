Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# La configuration du bootstrap est séparée de Léa afin que le profil 22K ne modifie jamais le registre 16K.
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$script:OpenHandsConfig = [ordered]@{
    ProjectRoot = $projectRoot
    StateRoot = Join-Path $projectRoot '.lea\openhands'
    StateFile = Join-Path $projectRoot '.lea\openhands\bootstrap-state.json'
    LogsRoot = Join-Path $projectRoot '.lea\openhands\logs'
    WorkspaceRoot = 'L:\IA_WORKSPACE'
    WorkspaceContainerPath = '/projects'
    StateVolume = 'lea_openhands_state'
    StateContainerPath = '/home/openhands/.openhands'
    ContainerName = 'lea-openhands'
    Image = 'ghcr.io/openhands/agent-canvas:1.15.0'
    ImageDigest = 'sha256:d42c7d70c604217afe64cefa19042e144df793f0d6c1d7c2914b0ed560d71cad'
    ContainerPort = 8000
    HostPort = 18000
    LlamaExecutable = Join-Path $projectRoot 'runtime\llama.cpp\llama-server.exe'
    ModelPath = Join-Path $projectRoot 'models\development\Qwen3-Coder-30B-A3B-Instruct-Q3_K_M.gguf'
    ModelSizeBytes = [int64]14711850144
    ModelSha256 = '30c83da425db2324444b6a6cecaf4c410038a2ec73a78de2436879dc0316a371'
    LlamaHost = '127.0.0.1'
    LlamaPort = 8081
    ModelAlias = 'lea-development-openhands'
    RequestedContext = 22000
    MinimumAvailableRamBytes = [int64](2.5GB)
    TargetAvailableRamBytes = [int64](3GB)
    CriticalAvailableRamBytes = [int64](1.5GB)
    ManagedLabel = 'com.projet-lea.openhands.managed'
    InstanceLabel = 'com.projet-lea.openhands.instance'
    SchemaLabel = 'com.projet-lea.openhands.schema'
}

# Retourne la configuration immuable partagée par les trois scripts publics.
function Get-OpenHandsConfig {
    return [pscustomobject]$script:OpenHandsConfig
}

# Lit une propriété JSON ou dictionnaire sans supposer le type PowerShell reçu.
function Get-OpenHandsObjectValue {
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

# Met à jour une propriété d'état sans dépendre de la représentation JSON ou dictionnaire.
function Set-OpenHandsObjectValue {
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

# Normalise un chemin Windows pour les comparaisons de sécurité sans accepter un chemin relatif ambigu.
function ConvertTo-OpenHandsCanonicalPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw 'Un chemin vide ne peut pas être normalisé.'
    }

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    return $fullPath.TrimEnd([char[]]@('\', '/'))
}

# Compare deux chemins canoniques indépendamment de la casse Windows.
function Test-OpenHandsSameCanonicalPath {
    param(
        [string]$Left,
        [string]$Right
    )

    if ([string]::IsNullOrWhiteSpace($Left) -or [string]::IsNullOrWhiteSpace($Right)) {
        return $false
    }

    try {
        $normalLeft = ConvertTo-OpenHandsCanonicalPath -Path $Left
        $normalRight = ConvertTo-OpenHandsCanonicalPath -Path $Right
    } catch {
        return $false
    }

    return [string]::Equals($normalLeft, $normalRight, [System.StringComparison]::OrdinalIgnoreCase)
}

# Exige que le seul bind mount de projets soit exactement L:\IA_WORKSPACE et jamais un alias ou reparse point.
function Assert-OpenHandsWorkspaceRoot {
    $config = Get-OpenHandsConfig
    $expectedPath = ConvertTo-OpenHandsCanonicalPath -Path $config.WorkspaceRoot
    $workspace = Get-Item -LiteralPath $expectedPath -Force -ErrorAction Stop

    if (-not $workspace.PSIsContainer) {
        throw "Le workspace OpenHands n’est pas un dossier : $expectedPath"
    }

    if (($workspace.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Le workspace OpenHands ne peut pas être un reparse point : $expectedPath"
    }

    if (-not (Test-OpenHandsSameCanonicalPath -Left $workspace.FullName -Right $expectedPath)) {
        throw "Le workspace résolu ne correspond pas exactement à L:\IA_WORKSPACE : $($workspace.FullName)"
    }

    return $workspace.FullName
}

# Accepte seulement la forme canonique Docker Desktop qui représente exactement le bind Windows L:\IA_WORKSPACE.
function Test-OpenHandsWorkspaceMountSource {
    param([Parameter(Mandatory = $true)][string]$Source)

    $config = Get-OpenHandsConfig
    if (Test-OpenHandsSameCanonicalPath -Left $Source -Right $config.WorkspaceRoot) {
        return $true
    }

    $drive = [System.IO.Path]::GetPathRoot($config.WorkspaceRoot).TrimEnd([char[]]@(':', '\')).ToLowerInvariant()
    $relativePath = $config.WorkspaceRoot.Substring(3).Replace('\', '/').Trim('/')
    $dockerDesktopPath = "/run/desktop/mnt/host/$drive/$relativePath"
    return [string]::Equals($Source.TrimEnd('/'), $dockerDesktopPath, [System.StringComparison]::Ordinal)
}

# Crée exclusivement les répertoires d'état ignorés du bootstrap, sans toucher à l'état de lea.ps1.
function Ensure-OpenHandsStateDirectories {
    $config = Get-OpenHandsConfig
    foreach ($path in @($config.StateRoot, $config.LogsRoot)) {
        if (Test-Path -LiteralPath $path) {
            $item = Get-Item -LiteralPath $path -Force
            if (-not $item.PSIsContainer) {
                throw "Le chemin d’état OpenHands n’est pas un dossier : $path"
            }
        } else {
            New-Item -ItemType Directory -Path $path -Force | Out-Null
        }
    }
}

# Calcule le hash d'une chaîne de contrôle sans persister de ligne de commande complète.
function Get-OpenHandsStringSha256 {
    param([Parameter(Mandatory = $true)][string]$Text)

    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
        return ([System.BitConverter]::ToString($sha256.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    } finally {
        $sha256.Dispose()
    }
}

# Lit l'état du bootstrap et refuse un JSON corrompu ou provenant d'un autre projet.
function Read-OpenHandsState {
    $config = Get-OpenHandsConfig
    if (-not (Test-Path -LiteralPath $config.StateFile)) {
        return $null
    }

    try {
        $state = Get-Content -LiteralPath $config.StateFile -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop
    } catch {
        throw "L’état OpenHands est illisible ; aucun processus ne sera adopté : $($_.Exception.Message)"
    }

    if ([int](Get-OpenHandsObjectValue -Object $state -Name 'schema_version') -ne 1) {
        throw 'L’état OpenHands utilise un schéma inconnu ; aucune action destructive n’est autorisée.'
    }

    if (-not (Test-OpenHandsSameCanonicalPath -Left ([string](Get-OpenHandsObjectValue -Object $state -Name 'project_root')) -Right $config.ProjectRoot)) {
        throw 'L’état OpenHands ne correspond pas à ce dépôt ; aucune action destructive n’est autorisée.'
    }

    return $state
}

# Écrit l'état dans le même volume via un remplacement atomique afin d'éviter un JSON partiel après interruption.
function Write-OpenHandsStateAtomically {
    param([Parameter(Mandatory = $true)]$State)

    Ensure-OpenHandsStateDirectories
    $config = Get-OpenHandsConfig
    $temporaryFile = "$($config.StateFile).$PID.$([guid]::NewGuid().ToString('N')).tmp"
    $backupFile = "$($config.StateFile).replace-backup"
    $utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
    $json = $State | ConvertTo-Json -Depth 12

    try {
        [System.IO.File]::WriteAllText($temporaryFile, $json, $utf8WithoutBom)
        if (Test-Path -LiteralPath $config.StateFile) {
            if (Test-Path -LiteralPath $backupFile) {
                Remove-Item -LiteralPath $backupFile -Force -ErrorAction Stop
            }

            [System.IO.File]::Replace($temporaryFile, $config.StateFile, $backupFile, $true)
        } else {
            [System.IO.File]::Move($temporaryFile, $config.StateFile)
        }
    } finally {
        if (Test-Path -LiteralPath $temporaryFile) {
            Remove-Item -LiteralPath $temporaryFile -Force -ErrorAction SilentlyContinue
        }

        if (Test-Path -LiteralPath $backupFile) {
            Remove-Item -LiteralPath $backupFile -Force -ErrorAction SilentlyContinue
        }
    }
}

# Construit un état initial qui identifie une instance précise avant tout lancement de processus ou conteneur.
function New-OpenHandsState {
    $config = Get-OpenHandsConfig
    return [ordered]@{
        schema_version = 1
        project_root = $config.ProjectRoot
        phase = 'starting'
        instance_id = [guid]::NewGuid().ToString('D')
        created_at_utc = [datetime]::UtcNow.ToString('o')
        updated_at_utc = [datetime]::UtcNow.ToString('o')
        container = [ordered]@{
            id = $null
            name = $config.ContainerName
            image = $config.Image
        }
        model = [ordered]@{
            launcher = $null
            listener = $null
            alias = $config.ModelAlias
            requested_context = $config.RequestedContext
        }
        mount_contract = [ordered]@{
            workspace_host = $config.WorkspaceRoot
            workspace_container = $config.WorkspaceContainerPath
            state_volume = $config.StateVolume
            state_container = $config.StateContainerPath
        }
        resources_at_model_ready = $null
        failure = $null
    }
}

# Marque une transition d'état horodatée sans effacer les preuves précédentes.
function Set-OpenHandsPhase {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)][ValidateSet('starting', 'running', 'stopped', 'failed')][string]$Phase,
        [string]$Failure = $null
    )

    Set-OpenHandsObjectValue -Object $State -Name 'phase' -Value $Phase
    Set-OpenHandsObjectValue -Object $State -Name 'updated_at_utc' -Value ([datetime]::UtcNow.ToString('o'))
    Set-OpenHandsObjectValue -Object $State -Name 'failure' -Value $Failure
}

# Récupère les PID qui écoutent réellement sur un port TCP, sans en déduire une propriété.
function Get-OpenHandsListeningPids {
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

# Refuse de démarrer sur un port occupé, car un PID trouvé par port n'est jamais considéré comme géré.
function Assert-OpenHandsPortFree {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $pids = @(Get-OpenHandsListeningPids -Port $Port)
    if ($pids.Count -gt 0) {
        throw "Le port $Port pour $Label est déjà utilisé par un processus non adopté (PID $($pids -join ', '))."
    }
}

# Attend la libération d'un port après l'arrêt d'un composant dont l'identité a déjà été vérifiée.
function Wait-ForOpenHandsPortRelease {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )

    $deadline = [datetime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([datetime]::UtcNow -lt $deadline) {
        if (@(Get-OpenHandsListeningPids -Port $Port).Count -eq 0) {
            return $true
        }

        Start-Sleep -Milliseconds 250
    }

    return @(Get-OpenHandsListeningPids -Port $Port).Count -eq 0
}

# Lit le chemin exécutable, en renvoyant null plutôt que d'assouplir une vérification d'identité.
function Get-OpenHandsProcessPath {
    param([Parameter(Mandatory = $true)][System.Diagnostics.Process]$Process)

    try {
        return $Process.Path
    } catch {
        return $null
    }
}

# Lit la ligne de commande uniquement pour l'empreinter, jamais pour la stocker telle quelle.
function Get-OpenHandsProcessCommandLine {
    param([Parameter(Mandatory = $true)][int]$ProcessId)

    try {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
        return [string]$process.CommandLine
    } catch {
        return $null
    }
}

# Crée une empreinte de processus incluant PID, nom, chemin, heure et hash de ligne de commande.
function New-OpenHandsProcessRecord {
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [Parameter(Mandatory = $true)][string]$ExpectedName,
        [Parameter(Mandatory = $true)][string]$ExpectedPath,
        [int]$Port = 0
    )

    $process = Get-Process -Id $ProcessId -ErrorAction Stop
    $actualPath = Get-OpenHandsProcessPath -Process $process
    $commandLine = Get-OpenHandsProcessCommandLine -ProcessId $ProcessId

    if ($process.ProcessName -ine $ExpectedName) {
        throw "Le PID $ProcessId n’est pas le processus attendu : $ExpectedName"
    }

    if ([string]::IsNullOrWhiteSpace($actualPath) -or -not (Test-OpenHandsSameCanonicalPath -Left $actualPath -Right $ExpectedPath)) {
        throw "Le chemin du PID $ProcessId ne peut pas être confirmé comme l’exécutable attendu."
    }

    if ([string]::IsNullOrWhiteSpace($commandLine)) {
        throw "La ligne de commande du PID $ProcessId ne peut pas être confirmée."
    }

    return [ordered]@{
        pid = [int]$process.Id
        process_name = $process.ProcessName
        executable_path = $actualPath
        start_time_utc = $process.StartTime.ToUniversalTime().ToString('o')
        command_line_sha256 = Get-OpenHandsStringSha256 -Text $commandLine
        port = [int]$Port
    }
}

# Produit un résultat de vérification uniforme pour que les appels d'arrêt restent fail-closed.
function New-OpenHandsProcessVerification {
    param(
        [bool]$Exists,
        [bool]$Verified,
        [bool]$Listening,
        $Process,
        [string]$Reason
    )

    return [pscustomobject]@{
        Exists = $Exists
        Verified = $Verified
        Listening = $Listening
        Process = $Process
        Reason = $Reason
    }
}

# Vérifie qu'un PID enregistré n'a ni été réemployé ni remplacé par un autre exécutable.
function Test-OpenHandsProcessRecord {
    param($Record)

    if ($null -eq $Record) {
        return New-OpenHandsProcessVerification -Exists $false -Verified $false -Listening $false -Process $null -Reason 'Aucun processus enregistré.'
    }

    $processId = [int](Get-OpenHandsObjectValue -Object $Record -Name 'pid')
    try {
        $process = Get-Process -Id $processId -ErrorAction Stop
    } catch {
        return New-OpenHandsProcessVerification -Exists $false -Verified $false -Listening $false -Process $null -Reason 'Le PID enregistré n’existe plus.'
    }

    try {
        if ($process.HasExited) {
            return New-OpenHandsProcessVerification -Exists $false -Verified $false -Listening $false -Process $null -Reason 'Le PID enregistré est terminé.'
        }
    } catch {
        return New-OpenHandsProcessVerification -Exists $true -Verified $false -Listening $false -Process $process -Reason 'La fin du PID ne peut pas être déterminée.'
    }

    $nameMatches = $process.ProcessName -ieq [string](Get-OpenHandsObjectValue -Object $Record -Name 'process_name')
    $pathMatches = $false
    $timeMatches = $false
    $commandLineMatches = $false

    try {
        $actualPath = Get-OpenHandsProcessPath -Process $process
        $pathMatches = -not [string]::IsNullOrWhiteSpace($actualPath) -and (Test-OpenHandsSameCanonicalPath -Left $actualPath -Right ([string](Get-OpenHandsObjectValue -Object $Record -Name 'executable_path')))
        $recordedTime = [datetime]::Parse([string](Get-OpenHandsObjectValue -Object $Record -Name 'start_time_utc')).ToUniversalTime()
        $timeMatches = [math]::Abs(($process.StartTime.ToUniversalTime() - $recordedTime).TotalSeconds) -lt 1
        $actualCommandLine = Get-OpenHandsProcessCommandLine -ProcessId $processId
        $commandLineMatches = -not [string]::IsNullOrWhiteSpace($actualCommandLine) -and ((Get-OpenHandsStringSha256 -Text $actualCommandLine) -eq [string](Get-OpenHandsObjectValue -Object $Record -Name 'command_line_sha256'))
    } catch {
        $pathMatches = $false
        $timeMatches = $false
        $commandLineMatches = $false
    }

    $port = [int](Get-OpenHandsObjectValue -Object $Record -Name 'port')
    $listening = $port -le 0 -or (@(Get-OpenHandsListeningPids -Port $port) -contains $processId)
    $verified = $nameMatches -and $pathMatches -and $timeMatches -and $commandLineMatches
    $reason = if ($verified) { 'Identité vérifiée.' } else { 'Le nom, chemin, heure ou hash de ligne de commande ne correspondent plus.' }

    return New-OpenHandsProcessVerification -Exists $true -Verified $verified -Listening $listening -Process $process -Reason $reason
}

# Récupère le parent d'un PID pour prouver qu'un écouteur appartient au lanceur créé par le script.
function Get-OpenHandsParentProcessId {
    param([Parameter(Mandatory = $true)][int]$ProcessId)

    try {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
        return [int]$process.ParentProcessId
    } catch {
        return 0
    }
}

# Vérifie toute la chaîne d'ascendance en évitant les boucles de PID anormales.
function Test-OpenHandsProcessDescendsFrom {
    param(
        [Parameter(Mandatory = $true)][int]$ChildProcessId,
        [Parameter(Mandatory = $true)][int]$AncestorProcessId
    )

    if ($ChildProcessId -eq $AncestorProcessId) {
        return $true
    }

    $visited = New-Object 'System.Collections.Generic.HashSet[int]'
    $current = $ChildProcessId
    while ($current -gt 0 -and $visited.Add($current)) {
        $parent = Get-OpenHandsParentProcessId -ProcessId $current
        if ($parent -eq $AncestorProcessId) {
            return $true
        }

        $current = $parent
    }

    return $false
}

# Refuse un écouteur qui ne descend pas réellement du launcher enregistré.
function Assert-OpenHandsListenerBelongsToLauncher {
    param(
        [Parameter(Mandatory = $true)][int]$ListenerProcessId,
        [Parameter(Mandatory = $true)][int]$LauncherProcessId
    )

    if (-not (Test-OpenHandsProcessDescendsFrom -ChildProcessId $ListenerProcessId -AncestorProcessId $LauncherProcessId)) {
        throw "Le PID d’écoute $ListenerProcessId n’appartient pas au launcher OpenHands $LauncherProcessId."
    }
}

# Arrête un processus uniquement après une vérification complète de son empreinte enregistrée.
function Stop-OpenHandsManagedProcess {
    param(
        [Parameter(Mandatory = $true)]$Record,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $check = Test-OpenHandsProcessRecord -Record $Record
    if (-not $check.Exists) {
        return
    }

    if (-not $check.Verified) {
        throw "Refus d’arrêter $Label : $($check.Reason)"
    }

    try {
        $check.Process | Stop-Process -Force -ErrorAction Stop
    } catch {
        # Le processus peut se terminer entre le dernier contrôle et l'arrêt demandé.
    }

    $deadline = [datetime]::UtcNow.AddSeconds(15)
    while ([datetime]::UtcNow -lt $deadline) {
        $after = Test-OpenHandsProcessRecord -Record $Record
        if (-not $after.Exists) {
            return
        }

        if (-not $after.Verified) {
            # Un PID réemployé ne doit jamais être arrêté une seconde fois.
            return
        }

        Start-Sleep -Milliseconds 250
    }

    throw "$Label n’a pas pu être arrêté dans le délai prévu."
}

# Lance docker.exe avec un tableau d'arguments, sans shell, interpolation de commande ni adoption implicite.
function Invoke-OpenHandsDocker {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$AllowFailure
    )

    $docker = (Get-Command docker.exe -ErrorAction Stop).Source
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = @(& $docker @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    $lines = @($output | ForEach-Object { [string]$_ })
    if ($exitCode -ne 0 -and -not $AllowFailure) {
        throw "docker $($Arguments -join ' ') a échoué (code $exitCode) : $($lines -join [Environment]::NewLine)"
    }

    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = $lines
    }
}

# Vérifie que le CLI cible bien le moteur local Docker Desktop Linux, jamais un contexte distant arbitraire.
function Assert-OpenHandsDockerReady {
    $version = Invoke-OpenHandsDocker -Arguments @('version', '--format', '{{.Server.Os}}|{{.Client.Context}}')
    $versionLine = [string]($version.Output | Select-Object -Last 1)
    $parts = $versionLine.Split('|')
    if ($parts.Count -ne 2 -or $parts[0] -ne 'linux' -or $parts[1] -ne 'desktop-linux') {
        throw "Docker Desktop Linux local est requis ; contexte obtenu : $versionLine"
    }

    $info = Invoke-OpenHandsDocker -Arguments @('info', '--format', '{{.OperatingSystem}}|{{.OSType}}')
    $infoLine = [string]($info.Output | Select-Object -Last 1)
    if ($infoLine -notmatch '^Docker Desktop\|linux$') {
        throw "Le moteur Docker attendu n’est pas Docker Desktop Linux : $infoLine"
    }
}

# Vérifie le GGUF imposé et les options réellement exposées par llama-server avant tout lancement.
function Assert-OpenHandsModelAndRuntime {
    $config = Get-OpenHandsConfig
    $model = Get-Item -LiteralPath $config.ModelPath -ErrorAction Stop
    if ($model.Length -ne $config.ModelSizeBytes) {
        throw "La taille du modèle est invalide : $($model.Length) octets au lieu de $($config.ModelSizeBytes)."
    }

    $hash = (Get-FileHash -LiteralPath $config.ModelPath -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
    if ($hash -ne $config.ModelSha256) {
        throw "Le SHA-256 du modèle est invalide : $hash"
    }

    if (-not (Test-Path -LiteralPath $config.LlamaExecutable -PathType Leaf)) {
        throw "llama-server.exe est introuvable : $($config.LlamaExecutable)"
    }

    $help = @(& $config.LlamaExecutable --help 2>&1) -join "`n"
    $requiredOptions = @('--host', '--port', '--alias', '--ctx-size', '--parallel', '--cache-type-k', '--cache-type-v', '--cache-ram', '--fit', '--fit-target', '--fit-ctx', '--gpu-layers', '--prio', '--mmap', '--threads', '--batch-size', '--ubatch-size', '--jinja')
    foreach ($option in $requiredOptions) {
        if ($help -notmatch [regex]::Escape($option)) {
            throw "La version locale de llama-server ne prend pas en charge l’option requise : $option"
        }
    }

    # La sortie --version de cette build Windows passe par stderr ; le help déjà capturé est la preuve fiable des options.
    return [pscustomobject]@{
        ModelPath = $model.FullName
        ModelSizeBytes = $model.Length
        Sha256 = $hash
        RuntimeVersion = 'llama-server options verified from --help'
    }
}

# Vérifie ou télécharge uniquement l'image stable épinglée, puis contrôle son digest publié.
function Ensure-OpenHandsImage {
    $config = Get-OpenHandsConfig
    $inspect = Invoke-OpenHandsDocker -Arguments @('image', 'inspect', $config.Image, '--format', '{{json .}}') -AllowFailure
    if ($inspect.ExitCode -ne 0) {
        Invoke-OpenHandsDocker -Arguments @('pull', $config.Image) | Out-Null
        $inspect = Invoke-OpenHandsDocker -Arguments @('image', 'inspect', $config.Image, '--format', '{{json .}}')
    }

    $image = (($inspect.Output -join "`n") | ConvertFrom-Json -ErrorAction Stop)
    $tags = @($image.RepoTags)
    $digests = @($image.RepoDigests)
    $expectedDigest = "$($config.Image.Split(':')[0])@$($config.ImageDigest)"
    if ($tags -notcontains $config.Image -or $digests -notcontains $expectedDigest) {
        throw "L’image Docker ne correspond pas au tag et digest OpenHands attendus : $($config.Image) / $expectedDigest"
    }

    return $image
}

# Vérifie un volume existant ou le crée avec des labels de propriété explicites, sans jamais adopter un volume homonyme.
function Ensure-OpenHandsStateVolume {
    $config = Get-OpenHandsConfig
    $inspect = Invoke-OpenHandsDocker -Arguments @('volume', 'inspect', $config.StateVolume, '--format', '{{json .}}') -AllowFailure
    if ($inspect.ExitCode -ne 0) {
        Invoke-OpenHandsDocker -Arguments @('volume', 'create', '--label', "$($config.ManagedLabel)=true", '--label', "$($config.SchemaLabel)=1", $config.StateVolume) | Out-Null
        $inspect = Invoke-OpenHandsDocker -Arguments @('volume', 'inspect', $config.StateVolume, '--format', '{{json .}}')
    }

    $volume = (($inspect.Output -join "`n") | ConvertFrom-Json -ErrorAction Stop)
    $labels = Get-OpenHandsObjectValue -Object $volume -Name 'Labels'
    if ([string](Get-OpenHandsObjectValue -Object $labels -Name $config.ManagedLabel) -ne 'true' -or [string](Get-OpenHandsObjectValue -Object $labels -Name $config.SchemaLabel) -ne '1') {
        throw "Le volume $($config.StateVolume) existe mais n’appartient pas au bootstrap OpenHands."
    }

    return $volume
}

# Inspecte un conteneur par ID ou nom sans considérer son simple nom comme une preuve de propriété.
function Get-OpenHandsContainerInspection {
    param([Parameter(Mandatory = $true)][string]$Identifier)

    $inspect = Invoke-OpenHandsDocker -Arguments @('container', 'inspect', $Identifier, '--format', '{{json .}}') -AllowFailure
    if ($inspect.ExitCode -ne 0) {
        return $null
    }

    try {
        return (($inspect.Output -join "`n") | ConvertFrom-Json -ErrorAction Stop)
    } catch {
        throw "L’inspection Docker du conteneur $Identifier est illisible."
    }
}

# Valide exhaustivement la provenance, les mounts, les labels et la publication loopback d'un conteneur OpenHands.
function Test-OpenHandsContainerContract {
    param(
        [Parameter(Mandatory = $true)]$Container,
        [Parameter(Mandatory = $true)]$State
    )

    $config = Get-OpenHandsConfig
    $reasons = @()
    $containerState = Get-OpenHandsObjectValue -Object $State -Name 'container'
    $recordedId = [string](Get-OpenHandsObjectValue -Object $containerState -Name 'id')
    $actualId = [string](Get-OpenHandsObjectValue -Object $Container -Name 'Id')
    if (-not [string]::IsNullOrWhiteSpace($recordedId) -and $actualId -ine $recordedId) {
        $reasons += 'L’ID Docker ne correspond pas à l’état enregistré.'
    }

    if ([string](Get-OpenHandsObjectValue -Object $Container -Name 'Name') -ne "/$($config.ContainerName)") {
        $reasons += 'Le nom Docker ne correspond pas au conteneur géré.'
    }

    $containerConfig = Get-OpenHandsObjectValue -Object $Container -Name 'Config'
    if ([string](Get-OpenHandsObjectValue -Object $containerConfig -Name 'Image') -ne $config.Image) {
        $reasons += 'L’image Docker ne correspond pas au tag épinglé.'
    }

    $labels = Get-OpenHandsObjectValue -Object $containerConfig -Name 'Labels'
    if ([string](Get-OpenHandsObjectValue -Object $labels -Name $config.ManagedLabel) -ne 'true') {
        $reasons += 'Le label de propriété OpenHands est absent.'
    }

    if ([string](Get-OpenHandsObjectValue -Object $labels -Name $config.SchemaLabel) -ne '1') {
        $reasons += 'Le label de schéma OpenHands est absent.'
    }

    if ([string](Get-OpenHandsObjectValue -Object $labels -Name $config.InstanceLabel) -ne [string](Get-OpenHandsObjectValue -Object $State -Name 'instance_id')) {
        $reasons += 'Le label d’instance ne correspond pas à l’état enregistré.'
    }

    $mounts = @((Get-OpenHandsObjectValue -Object $Container -Name 'Mounts'))
    $bindMounts = @($mounts | Where-Object { [string](Get-OpenHandsObjectValue -Object $_ -Name 'Type') -eq 'bind' })
    $volumeMounts = @($mounts | Where-Object { [string](Get-OpenHandsObjectValue -Object $_ -Name 'Type') -eq 'volume' })
    if ($mounts.Count -ne 2 -or $bindMounts.Count -ne 1 -or $volumeMounts.Count -ne 1) {
        $reasons += 'Le contrat impose exactement un bind projet et un volume d’état.'
    } else {
        $bind = $bindMounts[0]
        if (-not (Test-OpenHandsWorkspaceMountSource -Source ([string](Get-OpenHandsObjectValue -Object $bind -Name 'Source'))) -or [string](Get-OpenHandsObjectValue -Object $bind -Name 'Destination') -ne $config.WorkspaceContainerPath) {
            $reasons += 'Le bind de projets n’est pas exactement L:\IA_WORKSPACE vers /projects.'
        }

        $volume = $volumeMounts[0]
        if ([string](Get-OpenHandsObjectValue -Object $volume -Name 'Name') -ne $config.StateVolume -or [string](Get-OpenHandsObjectValue -Object $volume -Name 'Destination') -ne $config.StateContainerPath) {
            $reasons += 'Le volume d’état OpenHands ne correspond pas au contrat.'
        }
    }

    $hostConfig = Get-OpenHandsObjectValue -Object $Container -Name 'HostConfig'
    if ([bool](Get-OpenHandsObjectValue -Object $hostConfig -Name 'Privileged')) {
        $reasons += 'Le conteneur ne doit jamais être privilégié.'
    }

    $networkSettings = Get-OpenHandsObjectValue -Object $Container -Name 'NetworkSettings'
    $ports = Get-OpenHandsObjectValue -Object $networkSettings -Name 'Ports'
    $bindings = @((Get-OpenHandsObjectValue -Object $ports -Name '8000/tcp'))
    if ($bindings.Count -eq 0 -or $null -eq $bindings[0]) {
        # Docker vide NetworkSettings.Ports après stop ; HostConfig conserve alors le contrat de publication initial.
        $portBindings = Get-OpenHandsObjectValue -Object $hostConfig -Name 'PortBindings'
        $bindings = @((Get-OpenHandsObjectValue -Object $portBindings -Name '8000/tcp'))
    }

    if ($bindings.Count -ne 1 -or $null -eq $bindings[0]) {
        $reasons += 'Le port interne 8000 doit avoir une publication unique.'
    } else {
        $binding = $bindings[0]
        if ([string](Get-OpenHandsObjectValue -Object $binding -Name 'HostIp') -ne '127.0.0.1' -or [string](Get-OpenHandsObjectValue -Object $binding -Name 'HostPort') -ne [string]$config.HostPort) {
            $reasons += 'L’interface OpenHands doit être publiée seulement sur 127.0.0.1:18000.'
        }
    }

    $runtimeState = Get-OpenHandsObjectValue -Object $Container -Name 'State'
    return [pscustomobject]@{
        Exists = $true
        Verified = $reasons.Count -eq 0
        Running = [bool](Get-OpenHandsObjectValue -Object $runtimeState -Name 'Running')
        Container = $Container
        Reason = ($reasons -join ' ')
    }
}

# Vérifie le conteneur référencé par l'état ; un conteneur homonyme sans état valide reste inconnu.
function Test-OpenHandsManagedContainer {
    param([Parameter(Mandatory = $true)]$State)

    $containerState = Get-OpenHandsObjectValue -Object $State -Name 'container'
    $identifier = [string](Get-OpenHandsObjectValue -Object $containerState -Name 'id')
    if ([string]::IsNullOrWhiteSpace($identifier)) {
        $identifier = [string](Get-OpenHandsObjectValue -Object $containerState -Name 'name')
    }

    if ([string]::IsNullOrWhiteSpace($identifier)) {
        return [pscustomobject]@{ Exists = $false; Verified = $false; Running = $false; Container = $null; Reason = 'Aucun conteneur enregistré.' }
    }

    $container = Get-OpenHandsContainerInspection -Identifier $identifier
    if ($null -eq $container) {
        return [pscustomobject]@{ Exists = $false; Verified = $false; Running = $false; Container = $null; Reason = 'Le conteneur enregistré n’existe plus.' }
    }

    return Test-OpenHandsContainerContract -Container $container -State $State
}

# Attend l'endpoint OpenAI local et exige que l'alias dédié soit réellement déclaré par llama-server.
function Wait-ForOpenHandsLlamaEndpoint {
    param([Parameter(Mandatory = $true)][int]$TimeoutSeconds)

    $config = Get-OpenHandsConfig
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

    throw "llama-server OpenHands n’est pas prêt sur $uri après $TimeoutSeconds secondes : $lastError"
}

# Teste l'endpoint Windows après démarrage sans envoyer de prompt au modèle.
function Test-OpenHandsWindowsLlamaEndpoint {
    try {
        [void](Wait-ForOpenHandsLlamaEndpoint -TimeoutSeconds 5)
        return $true
    } catch {
        return $false
    }
}

# Mesure mémoire, pagefile, processus et GPU de façon informative sans jamais tuer un processus étranger.
function Get-OpenHandsResourceSnapshot {
    param($ModelRecord)

    $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
    $pagefile = @(Get-CimInstance Win32_PageFileUsage -ErrorAction SilentlyContinue | ForEach-Object {
        [ordered]@{
            name = $_.Name
            allocated_mb = $_.AllocatedBaseSize
            used_mb = $_.CurrentUsage
            peak_mb = $_.PeakUsage
        }
    })
    $modelCheck = Test-OpenHandsProcessRecord -Record $ModelRecord
    $modelMetrics = $null
    if ($modelCheck.Exists) {
        $modelMetrics = [ordered]@{
            pid = $modelCheck.Process.Id
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
    } catch {
        $gpu = $null
    }

    return [ordered]@{
        captured_at_utc = [datetime]::UtcNow.ToString('o')
        system_available_ram_bytes = [int64]($os.FreePhysicalMemory * 1KB)
        system_total_ram_bytes = [int64]($os.TotalVisibleMemorySize * 1KB)
        pagefile = $pagefile
        model = $modelMetrics
        gpu_csv = $gpu
    }
}

# Implique deux mesures espacées pour éviter d'accepter un état RAM transitoire juste après la readiness.
function Assert-OpenHandsReadyMemory {
    param([Parameter(Mandatory = $true)]$ModelRecord)

    $config = Get-OpenHandsConfig
    $samples = @(
        (Get-OpenHandsResourceSnapshot -ModelRecord $ModelRecord)
    )
    Start-Sleep -Seconds 5
    $samples += ,(Get-OpenHandsResourceSnapshot -ModelRecord $ModelRecord)
    $availableValues = @($samples | ForEach-Object { [int64]$_.system_available_ram_bytes })
    $criticalSamples = @($availableValues | Where-Object { $_ -lt $config.CriticalAvailableRamBytes })
    $minimumSamples = @($availableValues | Where-Object { $_ -lt $config.MinimumAvailableRamBytes })
    $targetSamples = @($availableValues | Where-Object { $_ -lt $config.TargetAvailableRamBytes })

    if ($criticalSamples.Count -gt 0) {
        throw "Mémoire critique pendant le lancement OpenHands : $([math]::Round(($availableValues | Measure-Object -Minimum).Minimum / 1GB, 2)) Gio disponibles."
    }

    if ($minimumSamples.Count -gt 0) {
        throw "Mémoire insuffisante pour le minimum nocturne OpenHands : $([math]::Round(($availableValues | Measure-Object -Minimum).Minimum / 1GB, 2)) Gio disponibles."
    }

    if ($targetSamples.Count -gt 0) {
        Write-Warning "La marge RAM OpenHands est sous l’objectif de 3 Gio, mais reste au-dessus du minimum temporaire."
    }

    return $samples[-1]
}

# Démarre exclusivement le llama-server séparé 22K et enregistre son identité avant d'attendre la readiness.
function Start-OpenHandsLlamaServer {
    param([Parameter(Mandatory = $true)]$State)

    $config = Get-OpenHandsConfig
    Assert-OpenHandsPortFree -Port $config.LlamaPort -Label 'llama-server OpenHands'
    Ensure-OpenHandsStateDirectories
    $stdinFile = Join-Path $config.StateRoot 'llama.stdin.empty'
    [System.IO.File]::WriteAllText($stdinFile, [string]::Empty)
    $timestamp = [datetime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    $stdoutLog = Join-Path $config.LogsRoot "llama-$timestamp.stdout.log"
    $stderrLog = Join-Path $config.LogsRoot "llama-$timestamp.stderr.log"
    $arguments = @(
        '-m', $config.ModelPath,
        '--host', $config.LlamaHost,
        '--port', [string]$config.LlamaPort,
        '--alias', $config.ModelAlias,
        '--ctx-size', [string]$config.RequestedContext,
        '--parallel', '1',
        '--cache-type-k', 'q4_0',
        '--cache-type-v', 'q4_0',
        '--cache-ram', '0',
        '--gpu-layers', 'auto',
        '--fit', 'on',
        '--fit-target', '1024',
        '--fit-ctx', [string]$config.RequestedContext,
        '--prio', '-1',
        '--mmap',
        '--threads', '8',
        '--batch-size', '512',
        '--ubatch-size', '128',
        '--jinja'
    )
    $process = $null
    $launcherRecord = $null

    try {
        $process = Start-Process -FilePath $config.LlamaExecutable -ArgumentList $arguments -WorkingDirectory $config.ProjectRoot -PassThru -WindowStyle Hidden -RedirectStandardInput $stdinFile -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog
        $launcherRecord = New-OpenHandsProcessRecord -ProcessId $process.Id -ExpectedName 'llama-server' -ExpectedPath $config.LlamaExecutable
        $modelState = Get-OpenHandsObjectValue -Object $State -Name 'model'
        Set-OpenHandsObjectValue -Object $modelState -Name 'launcher' -Value $launcherRecord
        Set-OpenHandsObjectValue -Object $modelState -Name 'listener' -Value $null
        Write-OpenHandsStateAtomically -State $State

        [void](Wait-ForOpenHandsLlamaEndpoint -TimeoutSeconds 240)
        $listeners = @(Get-OpenHandsListeningPids -Port $config.LlamaPort)
        if ($listeners.Count -ne 1) {
            throw "llama-server OpenHands doit posséder un seul PID d’écoute sur $($config.LlamaPort)."
        }

        Assert-OpenHandsListenerBelongsToLauncher -ListenerProcessId $listeners[0] -LauncherProcessId $process.Id
        $listenerRecord = New-OpenHandsProcessRecord -ProcessId $listeners[0] -ExpectedName 'llama-server' -ExpectedPath $config.LlamaExecutable -Port $config.LlamaPort
        Set-OpenHandsObjectValue -Object $modelState -Name 'listener' -Value $listenerRecord
        $snapshot = Assert-OpenHandsReadyMemory -ModelRecord $listenerRecord
        Set-OpenHandsObjectValue -Object $State -Name 'resources_at_model_ready' -Value $snapshot
        Write-OpenHandsStateAtomically -State $State
        return $State
    } catch {
        if ($null -ne $launcherRecord) {
            try {
                Stop-OpenHandsManagedProcess -Record $launcherRecord -Label 'llama-server OpenHands lancé pendant cette tentative'
            } catch {
                Write-Warning $_.Exception.Message
            }
        }

        Set-OpenHandsPhase -State $State -Phase 'failed' -Failure $_.Exception.Message
        Write-OpenHandsStateAtomically -State $State
        throw
    }
}

# Démarre ou reprend uniquement le conteneur dont les labels et mounts satisfont intégralement le contrat enregistré.
function Start-OpenHandsManagedContainer {
    param([Parameter(Mandatory = $true)]$State)

    $config = Get-OpenHandsConfig
    $existingByName = Get-OpenHandsContainerInspection -Identifier $config.ContainerName
    if ($null -ne $existingByName) {
        $contract = Test-OpenHandsContainerContract -Container $existingByName -State $State
        if (-not $contract.Verified) {
            throw "Un conteneur nommé $($config.ContainerName) existe mais n’est pas adopté : $($contract.Reason)"
        }

        if ($contract.Running) {
            throw 'Double démarrage OpenHands refusé : le conteneur géré est déjà actif.'
        }

        Invoke-OpenHandsDocker -Arguments @('container', 'start', [string](Get-OpenHandsObjectValue -Object $existingByName -Name 'Id')) | Out-Null
        return $contract.Container
    }

    Ensure-OpenHandsStateVolume | Out-Null
    $workspace = Assert-OpenHandsWorkspaceRoot
    $bindMount = "type=bind,src=$workspace,dst=$($config.WorkspaceContainerPath)"
    $stateMount = "type=volume,src=$($config.StateVolume),dst=$($config.StateContainerPath)"
    $run = Invoke-OpenHandsDocker -Arguments @(
        'container', 'run', '--detach',
        '--name', $config.ContainerName,
        '--label', "$($config.ManagedLabel)=true",
        '--label', "$($config.InstanceLabel)=$([string](Get-OpenHandsObjectValue -Object $State -Name 'instance_id'))",
        '--label', "$($config.SchemaLabel)=1",
        '--publish', "127.0.0.1:$($config.HostPort):$($config.ContainerPort)",
        '--mount', $stateMount,
        '--mount', $bindMount,
        $config.Image
    )
    $containerId = ([string]($run.Output | Select-Object -Last 1)).Trim()
    if ($containerId -notmatch '^[0-9a-f]{64}$') {
        throw "Docker n’a pas retourné un ID de conteneur valide : $containerId"
    }

    $containerState = Get-OpenHandsObjectValue -Object $State -Name 'container'
    Set-OpenHandsObjectValue -Object $containerState -Name 'id' -Value $containerId
    Write-OpenHandsStateAtomically -State $State
    $container = Get-OpenHandsContainerInspection -Identifier $containerId
    $contract = Test-OpenHandsContainerContract -Container $container -State $State
    if (-not $contract.Verified) {
        throw "Le conteneur créé ne respecte pas le contrat OpenHands : $($contract.Reason)"
    }

    return $container
}

# Attend l'UI locale publiée sur loopback sans confondre une réponse réseau avec une exposition LAN.
function Wait-ForOpenHandsUi {
    param([Parameter(Mandatory = $true)][int]$TimeoutSeconds)

    $config = Get-OpenHandsConfig
    $uri = "http://127.0.0.1:$($config.HostPort)/canvas"
    $deadline = [datetime]::UtcNow.AddSeconds($TimeoutSeconds)
    $lastError = $null
    while ([datetime]::UtcNow -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                return $uri
            }
        } catch {
            $lastError = $_.Exception.Message
        }

        Start-Sleep -Milliseconds 500
    }

    throw "L’UI OpenHands ne répond pas sur $uri après $TimeoutSeconds secondes : $lastError"
}

# Vérifie depuis le conteneur réel que Docker Desktop atteint l'API modèle via host.docker.internal.
function Test-OpenHandsContainerLlamaEndpoint {
    param([Parameter(Mandatory = $true)]$State)

    $config = Get-OpenHandsConfig
    $check = Test-OpenHandsManagedContainer -State $State
    if (-not $check.Exists -or -not $check.Verified -or -not $check.Running) {
        throw "Le conteneur OpenHands n’est pas prêt pour le test LLM : $($check.Reason)"
    }

    $containerId = [string](Get-OpenHandsObjectValue -Object $check.Container -Name 'Id')
    $python = "import json, urllib.request; data=json.load(urllib.request.urlopen('http://host.docker.internal:$($config.LlamaPort)/v1/models', timeout=10)); assert any(item.get('id') == '$($config.ModelAlias)' for item in data.get('data', [])); print('$($config.ModelAlias)')"
    $result = Invoke-OpenHandsDocker -Arguments @('container', 'exec', $containerId, 'python', '-c', $python)
    if (([string]($result.Output -join "`n")).Trim() -ne $config.ModelAlias) {
        throw 'Le test depuis le conteneur ne confirme pas l’alias du modèle OpenHands.'
    }

    return $true
}

# Réduit une vérification de PID à des données sérialisables afin que status ne divulgue ni objet Process ni détails inutiles.
function ConvertTo-OpenHandsProcessStatus {
    param($Check)

    if ($null -eq $Check) {
        return $null
    }

    $processId = $null
    if ($Check.Exists -and $null -ne $Check.Process) {
        $processId = [int]$Check.Process.Id
    }

    return [pscustomobject]@{
        exists = [bool]$Check.Exists
        verified = [bool]$Check.Verified
        listening = [bool]$Check.Listening
        pid = $processId
        reason = [string]$Check.Reason
    }
}

# Réduit l'inspection Docker à la preuve de contrat utile au statut sans exposer la configuration complète du conteneur.
function ConvertTo-OpenHandsContainerStatus {
    param($Check)

    if ($null -eq $Check) {
        return $null
    }

    $containerId = $null
    $imageId = $null
    if ($Check.Exists -and $null -ne $Check.Container) {
        $containerId = [string](Get-OpenHandsObjectValue -Object $Check.Container -Name 'Id')
        $imageId = [string](Get-OpenHandsObjectValue -Object $Check.Container -Name 'Image')
    }

    return [pscustomobject]@{
        exists = [bool]$Check.Exists
        verified = [bool]$Check.Verified
        running = [bool]$Check.Running
        id = $containerId
        image_id = $imageId
        reason = [string]$Check.Reason
    }
}

# Construit un état lisible sans modifier les processus, même lorsque l'état local est absent ou ambigu.
function Get-OpenHandsStatus {
    $config = Get-OpenHandsConfig
    $state = $null
    $stateError = $null
    try {
        $state = Read-OpenHandsState
    } catch {
        $stateError = $_.Exception.Message
    }

    $dockerReady = $false
    $dockerError = $null
    try {
        Assert-OpenHandsDockerReady
        $dockerReady = $true
    } catch {
        $dockerError = $_.Exception.Message
    }

    $containerCheck = $null
    $launcherCheck = $null
    $listenerCheck = $null
    if ($null -ne $state) {
        if ($dockerReady) {
            $containerCheck = Test-OpenHandsManagedContainer -State $state
        }

        $model = Get-OpenHandsObjectValue -Object $state -Name 'model'
        $launcherCheck = Test-OpenHandsProcessRecord -Record (Get-OpenHandsObjectValue -Object $model -Name 'launcher')
        $listenerCheck = Test-OpenHandsProcessRecord -Record (Get-OpenHandsObjectValue -Object $model -Name 'listener')
    }

    $resources = $null
    try {
        $resources = Get-OpenHandsResourceSnapshot -ModelRecord $(if ($null -eq $state) { $null } else { Get-OpenHandsObjectValue -Object (Get-OpenHandsObjectValue -Object $state -Name 'model') -Name 'listener' })
    } catch {
        $resources = $null
    }

    return [pscustomobject]@{
        state = $state
        state_error = $stateError
        docker_ready = $dockerReady
        docker_error = $dockerError
        container = ConvertTo-OpenHandsContainerStatus -Check $containerCheck
        model_launcher = ConvertTo-OpenHandsProcessStatus -Check $launcherCheck
        model_listener = ConvertTo-OpenHandsProcessStatus -Check $listenerCheck
        ui_url = "http://127.0.0.1:$($config.HostPort)/canvas"
        model_url = "http://$($config.LlamaHost):$($config.LlamaPort)/v1/models"
        workspace = $config.WorkspaceRoot
        resources = $resources
    }
}

# Arrête seulement le conteneur et les PID qui correspondent simultanément à l'état enregistré et au contrat de propriété.
function Stop-OpenHandsManagedInstance {
    param([Parameter(Mandatory = $true)]$State)

    $config = Get-OpenHandsConfig
    $containerCheck = Test-OpenHandsManagedContainer -State $State
    if ($containerCheck.Exists -and -not $containerCheck.Verified) {
        throw "Refus d’arrêter le conteneur OpenHands : $($containerCheck.Reason)"
    }

    $model = Get-OpenHandsObjectValue -Object $State -Name 'model'
    $launcherRecord = Get-OpenHandsObjectValue -Object $model -Name 'launcher'
    $listenerRecord = Get-OpenHandsObjectValue -Object $model -Name 'listener'
    $launcherCheck = Test-OpenHandsProcessRecord -Record $launcherRecord
    $listenerCheck = Test-OpenHandsProcessRecord -Record $listenerRecord
    if ($launcherCheck.Exists -and -not $launcherCheck.Verified) {
        throw "Refus d’arrêter llama-server : $($launcherCheck.Reason)"
    }

    if ($listenerCheck.Exists -and -not $listenerCheck.Verified) {
        throw "Refus d’arrêter l’écouteur llama-server : $($listenerCheck.Reason)"
    }

    if ($containerCheck.Exists -and $containerCheck.Running) {
        Invoke-OpenHandsDocker -Arguments @('container', 'stop', '--time', '30', [string](Get-OpenHandsObjectValue -Object $containerCheck.Container -Name 'Id')) | Out-Null
    }

    if ($listenerCheck.Exists -and $listenerCheck.Process.Id -ne $launcherCheck.Process.Id) {
        Stop-OpenHandsManagedProcess -Record $listenerRecord -Label 'écouteur llama-server OpenHands'
    }

    if ($launcherCheck.Exists) {
        Stop-OpenHandsManagedProcess -Record $launcherRecord -Label 'llama-server OpenHands'
    }

    if (-not (Wait-ForOpenHandsPortRelease -Port $config.HostPort -TimeoutSeconds 30)) {
        throw "Le port $($config.HostPort) reste occupé ; aucun PID inconnu ne sera arrêté."
    }

    if (-not (Wait-ForOpenHandsPortRelease -Port $config.LlamaPort -TimeoutSeconds 30)) {
        throw "Le port $($config.LlamaPort) reste occupé ; aucun PID inconnu ne sera arrêté."
    }

    Set-OpenHandsPhase -State $State -Phase 'stopped'
    Write-OpenHandsStateAtomically -State $State
    return $State
}

Export-ModuleMember -Function @(
    'Get-OpenHandsConfig',
    'Assert-OpenHandsWorkspaceRoot',
    'Ensure-OpenHandsStateDirectories',
    'Read-OpenHandsState',
    'Write-OpenHandsStateAtomically',
    'New-OpenHandsState',
    'Set-OpenHandsPhase',
    'Assert-OpenHandsDockerReady',
    'Assert-OpenHandsModelAndRuntime',
    'Ensure-OpenHandsImage',
    'Ensure-OpenHandsStateVolume',
    'Assert-OpenHandsPortFree',
    'Start-OpenHandsLlamaServer',
    'Start-OpenHandsManagedContainer',
    'Wait-ForOpenHandsUi',
    'Test-OpenHandsWindowsLlamaEndpoint',
    'Test-OpenHandsContainerLlamaEndpoint',
    'Test-OpenHandsManagedContainer',
    'Get-OpenHandsStatus',
    'Stop-OpenHandsManagedInstance',
    'Get-OpenHandsResourceSnapshot'
)
