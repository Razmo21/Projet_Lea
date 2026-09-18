param(
    [Parameter(Position = 0)]
    [string]$Action,
    [string]$ProfileId,
    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

if ($Json) {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
}

$ProjectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$StateDirectory = Join-Path $ProjectRoot '.lea'
$StateFile = Join-Path $StateDirectory 'processes.json'
$StandardInputFile = Join-Path $StateDirectory 'stdin.empty'
$TaskkillExecutable = Join-Path $env:SystemRoot 'System32\taskkill.exe'
$NetstatExecutable = Join-Path $env:SystemRoot 'System32\netstat.exe'

# Résout un fichier du registre sans accepter un chemin qui sortirait du projet.
function Resolve-RegistryFile {
    # Résout un chemin relatif du registre et refuse toute sortie de la racine autorisée.
    param(
        [Parameter(Mandatory = $true)][string]$RelativePath,
        [Parameter(Mandatory = $true)][string]$AllowedRoot,
        [Parameter(Mandatory = $true)][string]$Label
    )

    if ([string]::IsNullOrWhiteSpace($RelativePath) -or [System.IO.Path]::IsPathRooted($RelativePath)) {
        throw "$Label doit être un chemin relatif au projet."
    }

    $parts = @($RelativePath -split '[\\/]+' | Where-Object { $_ -ne '' })
    if ($parts -contains '..') {
        throw "$Label ne peut pas contenir '..'."
    }

    $resolvedAllowedRoot = [System.IO.Path]::GetFullPath($AllowedRoot).TrimEnd('\')
    $resolved = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot ($RelativePath -replace '/', '\')))
    if (-not $resolved.StartsWith($resolvedAllowedRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "$Label sort de sa racine autorisée."
    }

    return $resolved
}

# Retourne exactement un profil du registre ou signale une configuration ambiguë.
function Get-RegistryProfile {
    # Retourne exactement le profil demandé sans bascule silencieuse vers Général.
    param(
        [Parameter(Mandatory = $true)]$Registry,
        [Parameter(Mandatory = $true)][string]$ProfileId
    )

    $matches = @($Registry.profiles | Where-Object { $_.id -eq $ProfileId })
    if ($matches.Count -ne 1) {
        throw "Profil de modèle introuvable ou dupliqué : $ProfileId"
    }

    return $matches[0]
}

# Charge et valide les invariants communs du registre avant tout démarrage.
function Read-ModelRegistry {
    # Valide les champs critiques utilisés par PowerShell avant tout lancement de processus.
    param([Parameter(Mandatory = $true)][string]$RegistryPath)

    if (-not (Test-Path -LiteralPath $RegistryPath -PathType Leaf)) {
        throw "Registre des modèles introuvable : $RegistryPath"
    }

    try {
        $registry = Get-Content -Raw -Encoding UTF8 -LiteralPath $RegistryPath | ConvertFrom-Json
    } catch {
        throw "Registre des modèles invalide : $($_.Exception.Message)"
    }

    $schemaVersion = $registry.PSObject.Properties['schema_version']
    $defaultProfileId = $registry.PSObject.Properties['default_profile_id']
    if ($null -eq $schemaVersion -or
        ($schemaVersion.Value -isnot [int] -and $schemaVersion.Value -isnot [long]) -or
        [int64]$schemaVersion.Value -lt 1 -or
        $null -eq $defaultProfileId -or
        $defaultProfileId.Value -isnot [string] -or
        [string]::IsNullOrWhiteSpace([string]$defaultProfileId.Value)) {
        throw 'Le registre des modèles ne possède pas de version ou de profil par défaut valide.'
    }

    # Le lanceur utilise ces valeurs pour l'unique serveur llama.cpp : elles ne
    # peuvent donc ni désigner une écoute publique ni diverger de ses routes API.
    $runtimeProperty = $registry.PSObject.Properties['runtime']
    if ($null -eq $runtimeProperty -or $null -eq $runtimeProperty.Value) {
        throw 'Le registre des modèles ne définit pas le runtime llama.cpp.'
    }
    $runtime = $runtimeProperty.Value
    $runtimeHost = $runtime.PSObject.Properties['host']
    $runtimePort = $runtime.PSObject.Properties['port']
    $chatPath = $runtime.PSObject.Properties['chat_completions_path']
    $modelsPath = $runtime.PSObject.Properties['models_path']
    if ($null -eq $runtimeHost -or [string]$runtimeHost.Value -ne '127.0.0.1') {
        throw 'Le runtime doit écouter exclusivement sur 127.0.0.1.'
    }
    if ($null -eq $runtimePort -or
        ($runtimePort.Value -isnot [int] -and $runtimePort.Value -isnot [long]) -or
        [int64]$runtimePort.Value -lt 1 -or [int64]$runtimePort.Value -gt 65535) {
        throw 'Le port du runtime doit être compris entre 1 et 65535.'
    }
    if ($null -eq $chatPath -or $null -eq $modelsPath -or
        -not ([string]$chatPath.Value).StartsWith('/') -or
        -not ([string]$modelsPath.Value).StartsWith('/')) {
        throw "Les routes du runtime doivent commencer par '/'."
    }

    $profileIds = @{}
    $aliases = @{}
    $knownTypes = @($registry.model_types)
    $knownCapabilities = @($registry.capability_catalog.PSObject.Properties.Name)
    $knownTools = @($registry.tool_catalog)
    $knownPermissions = @($registry.workspace_permissions.PSObject.Properties.Name)
    $resourcePoliciesProperty = $registry.PSObject.Properties['resource_policies']
    if ($null -eq $resourcePoliciesProperty -or $null -eq $resourcePoliciesProperty.Value) {
        throw 'Le registre des modèles ne définit pas les politiques de ressources.'
    }
    $resourcePolicies = $resourcePoliciesProperty.Value
    $policyProperties = @($resourcePolicies.PSObject.Properties)
    if ($policyProperties.Count -eq 0) {
        throw 'Le registre des modèles ne définit aucune politique de ressources.'
    }
    $maxRuntimeHardLimitBytes = [int64]24 * 1024 * 1024 * 1024
    foreach ($policyProperty in $policyProperties) {
        $policyName = [string]$policyProperty.Name
        $policy = $policyProperty.Value
        if ([string]::IsNullOrWhiteSpace($policyName) -or $null -eq $policy) {
            throw 'Une politique de ressources est invalide.'
        }
        foreach ($fieldName in @(
            'runtime_warning_bytes',
            'runtime_hard_limit_bytes',
            'system_available_warning_bytes',
            'system_available_critical_bytes',
            'vram_target_free_mib',
            'max_threads'
        )) {
            $field = $policy.PSObject.Properties[$fieldName]
            if ($null -eq $field -or
                ($field.Value -isnot [int] -and $field.Value -isnot [long]) -or
                [int64]$field.Value -le 0) {
                throw "La politique de ressources $policyName possède un champ $fieldName invalide."
            }
        }
        $priority = $policy.PSObject.Properties['cpu_priority']
        if ($null -eq $priority -or
            $priority.Value -isnot [string] -or
            @('idle', 'below_normal', 'normal') -notcontains [string]$priority.Value) {
            throw "La politique de ressources $policyName possède une priorité CPU invalide."
        }
        if ([int64]$policy.runtime_warning_bytes -ge [int64]$policy.runtime_hard_limit_bytes -or
            [int64]$policy.runtime_hard_limit_bytes -ge $maxRuntimeHardLimitBytes) {
            throw "La limite RAM dure de la politique $policyName doit rester strictement inférieure à 24 GiB."
        }
        if ([int64]$policy.system_available_critical_bytes -ge [int64]$policy.system_available_warning_bytes) {
            throw "Les seuils RAM système de la politique $policyName sont inversés."
        }
        if ([int64]$policy.vram_target_free_mib -lt 800 -or [int64]$policy.vram_target_free_mib -gt 1024) {
            throw "La marge VRAM de la politique $policyName doit rester entre 800 et 1024 MiB."
        }
        if ([int64]$policy.max_threads -gt 64) {
            throw "Le nombre de threads de la politique $policyName est invalide."
        }
    }
    $knownPolicies = @($policyProperties.Name)

    foreach ($profile in @($registry.profiles)) {
        $enabled = $profile.PSObject.Properties['enabled']
        $contextTokens = $profile.PSObject.Properties['context_tokens']
        $runtimeDefinition = $profile.PSObject.Properties['runtime']
        if ($null -eq $enabled -or $enabled.Value -isnot [bool] -or
            $null -eq $contextTokens -or
            ($contextTokens.Value -isnot [int] -and $contextTokens.Value -isnot [long]) -or
            $null -eq $runtimeDefinition -or $null -eq $runtimeDefinition.Value) {
            throw 'Un profil contient un type JSON invalide.'
        }
        $profileRuntime = $runtimeDefinition.Value
        $parallelSlots = $profileRuntime.PSObject.Properties['parallel_slots']
        $threads = $profileRuntime.PSObject.Properties['threads']
        if ($null -eq $parallelSlots -or
            ($parallelSlots.Value -isnot [int] -and $parallelSlots.Value -isnot [long]) -or
            $null -eq $threads -or
            ($threads.Value -isnot [int] -and $threads.Value -isnot [long])) {
            throw 'Le nombre de slots et de threads du profil doit être un entier JSON.'
        }
        foreach ($booleanName in @('jinja', 'mmap', 'fit', 'cache_ram', 'skip_chat_parsing')) {
            $booleanProperty = $profileRuntime.PSObject.Properties[$booleanName]
            if ($null -eq $booleanProperty -or $booleanProperty.Value -isnot [bool]) {
                throw "Le champ $booleanName du profil doit être un booléen JSON."
            }
        }
        $profileId = [string]$profile.id
        if ($profileId -notmatch '^[a-z][a-z0-9_-]{1,31}$' -or $profileIds.ContainsKey($profileId)) {
            throw "Identifiant de profil invalide ou dupliqué : $profileId"
        }
        $profileIds[$profileId] = $true

        $alias = [string]$profile.runtime.alias
        if ([string]::IsNullOrWhiteSpace($alias) -or $aliases.ContainsKey($alias)) {
            throw "Alias llama.cpp vide ou dupliqué : $alias"
        }
        $aliases[$alias] = $true

        if ([string]::IsNullOrWhiteSpace([string]$profile.display_name) -or $knownTypes -notcontains [string]$profile.model_type) {
            throw "Nom ou type invalide pour le profil $profileId."
        }
        if ([int64]$contextTokens.Value -le 0 -or [int64]$parallelSlots.Value -ne 1) {
            throw "Contexte ou nombre de slots invalide pour le profil $profileId."
        }
        if ($profileId -eq 'development' -and @(16000, 18000, 20000, 22000) -notcontains [int64]$contextTokens.Value) {
            throw 'Le profil development doit utiliser une fenêtre Stage 10 autorisée : 16K, 18K, 20K ou 22K.'
        }
        foreach ($engineField in @('model_name', 'agent_engine', 'orchestrator')) {
            $engineProperty = $profile.PSObject.Properties[$engineField]
            if ($null -eq $engineProperty -or [string]::IsNullOrWhiteSpace([string]$engineProperty.Value)) {
                throw "Le profil $profileId ne définit pas $engineField."
            }
        }
        $gpuLayers = [string]$profile.runtime.gpu_layers
        if ($gpuLayers -ne 'auto' -and $gpuLayers -notmatch '^\d{1,3}$') {
            throw "Nombre de couches GPU invalide pour le profil $profileId."
        }
        if ($gpuLayers -eq 'auto' -and -not [bool]$profile.runtime.fit) {
            throw "Le profil $profileId ne peut utiliser gpu_layers=auto sans --fit."
        }
        if ([bool]$profile.runtime.fit -and [int]$profile.runtime.fit_context_min_tokens -ne [int]$profile.context_tokens) {
            throw "Le profil $profileId autoriserait --fit à réduire silencieusement son contexte."
        }
        if (@('f16', 'q8_0', 'q4_0') -notcontains [string]$profile.runtime.cache_type_k -or @('f16', 'q8_0', 'q4_0') -notcontains [string]$profile.runtime.cache_type_v) {
            throw "Cache KV invalide pour le profil $profileId."
        }
        if ([string]$profile.expected_sha256 -notmatch '^[0-9a-f]{64}$') {
            throw "SHA-256 attendu invalide pour le profil $profileId."
        }
        if ($knownPermissions -notcontains [string]$profile.workspace_permission -or $knownPolicies -notcontains [string]$profile.resource_policy) {
            throw "Permission workspace ou politique de ressources inconnue pour $profileId."
        }
        $resourcePolicy = $resourcePolicies.PSObject.Properties[[string]$profile.resource_policy].Value
        if ([int64]$threads.Value -gt [int64]$resourcePolicy.max_threads) {
            throw "Le profil $profileId dépasse le nombre de threads autorisé."
        }
        foreach ($capability in @($profile.capabilities)) {
            if ($knownCapabilities -notcontains [string]$capability) {
                throw "Capacité inconnue pour $profileId : $capability"
            }
        }
        foreach ($tool in @($profile.tools)) {
            if ($knownTools -notcontains [string]$tool) {
                throw "Outil inconnu pour $profileId : $tool"
            }
        }

        $modelFile = Resolve-RegistryFile -RelativePath ([string]$profile.model_path) -AllowedRoot (Join-Path $ProjectRoot 'models') -Label "Modèle $profileId"
        if ([bool]$profile.enabled -and -not (Test-Path -LiteralPath $modelFile -PathType Leaf)) {
            throw "Modèle activé introuvable pour $profileId : $modelFile"
        }
        foreach ($promptPath in @($profile.prompt.reliability_path, $profile.prompt.profile_path, $profile.prompt.memory_path)) {
            $promptFile = Resolve-RegistryFile -RelativePath ([string]$promptPath) -AllowedRoot (Join-Path $ProjectRoot 'config\prompts') -Label "Prompt $profileId"
            if (-not (Test-Path -LiteralPath $promptFile -PathType Leaf)) {
                throw "Prompt introuvable pour $profileId : $promptFile"
            }
        }
    }

    if (-not $profileIds.ContainsKey([string]$registry.default_profile_id)) {
        throw 'Le profil par défaut du registre est introuvable.'
    }
    $defaultProfile = Get-RegistryProfile -Registry $registry -ProfileId ([string]$registry.default_profile_id)
    if (-not [bool]$defaultProfile.enabled) {
        throw 'Le profil par défaut doit être activé.'
    }

    # Le lanceur direct n'est autorisé que pour Général. Programmation est
    # orchestré par OpenHands sur son endpoint séparé et ne doit jamais être
    # lancé accidentellement sur le port général.
    $developmentProfile = Get-RegistryProfile -Registry $registry -ProfileId 'development'
    $openHands = $registry.PSObject.Properties['openhands']
    if ($null -eq $openHands -or $null -eq $openHands.Value -or
        [string]$developmentProfile.model_name -ne 'Qwen2.5-Coder-7B-Instruct Q6_K' -or
        [string]$developmentProfile.agent_engine -ne 'OpenHands' -or
        [string]$developmentProfile.orchestrator -ne 'agent_server_sdk' -or
        @(16000, 18000, 20000, 22000) -notcontains [int]$developmentProfile.context_tokens) {
        throw 'Le profil Programmation doit être le profil OpenHands Qwen2.5 avec une fenêtre Stage 10 autorisée.'
    }
    $agentServer = $openHands.Value.agent_server
    $modelEndpoint = $openHands.Value.model_endpoint
    if ($null -eq $agentServer -or $null -eq $modelEndpoint -or
        [string]$agentServer.host -ne '127.0.0.1' -or
        [string]$modelEndpoint.host -ne '127.0.0.1' -or
        [int]$modelEndpoint.port -eq [int]$runtime.port -or
        @($agentServer.tool_names).Count -ne 3 -or
        @($agentServer.tool_names | Sort-Object -Unique) -join ',' -ne 'file_editor,task_tracker,terminal') {
        throw 'La configuration OpenHands du registre est invalide.'
    }

    return $registry
}

$ModelRegistryPath = Join-Path $ProjectRoot 'config\models.json'
$ModelRegistry = Read-ModelRegistry -RegistryPath $ModelRegistryPath
$DefaultProfileId = [string]$ModelRegistry.default_profile_id
$DefaultProfile = Get-RegistryProfile -Registry $ModelRegistry -ProfileId $DefaultProfileId
$ModelExecutable = Resolve-RegistryFile -RelativePath ([string]$ModelRegistry.runtime.executable) -AllowedRoot (Join-Path $ProjectRoot 'runtime\llama.cpp') -Label 'Runtime llama.cpp'
$ModelRuntimeHost = [string]$ModelRegistry.runtime.host
$ModelRuntimePort = [int]$ModelRegistry.runtime.port
$ModelRuntimeModelsEndpoint = 'http://{0}:{1}{2}' -f $ModelRuntimeHost, $ModelRuntimePort, [string]$ModelRegistry.runtime.models_path
$BackendDirectory = Join-Path $ProjectRoot 'backend'
$BackendPython = Join-Path $BackendDirectory '.venv\Scripts\python.exe'
$DevelopmentRuntimeScript = Join-Path $ProjectRoot 'tools\openhands\development_runtime.py'
$PackageFile = Join-Path $ProjectRoot 'package.json'

$ComponentDefinitions = [ordered]@{
    model = [ordered]@{
        Label = 'Modèle'
        Port = $ModelRuntimePort
        ExpectedName = 'llama-server'
        ExpectedPath = $ModelExecutable
        Endpoint = $ModelRuntimeModelsEndpoint
        ExpectedContent = $null
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

$AllComponentNames = @('model', 'backend', 'frontend')
$CoreComponentNames = @('model', 'backend')

$KnownStateFiles = @(
    'processes.json',
    'stdin.empty',
    'model.stdout.log',
    'model.stderr.log',
    'backend.stdout.log',
    'backend.stderr.log',
    'frontend.stdout.log',
    'frontend.stderr.log'
)

# Lit le parent d'un PID sans supposer que le processus existe encore.
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

# Vérifie une filiation de processus bornée avant d'attribuer un enfant à Léa.
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

# Énumère les descendants connus d'un processus déjà identifié.
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

# Refuse d'adopter un port dont l'écouteur ne descend pas du lanceur attendu.
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

# Affiche les seules commandes publiques prises en charge par le lanceur.
function Write-Usage {
    Write-Host 'Usage:'
    Write-Host '  .\lea.ps1 start'
    Write-Host '  .\lea.ps1 status'
    Write-Host '  .\lea.ps1 stop'
    Write-Host '  .\lea.ps1 start-core'
    Write-Host '  .\lea.ps1 status-core [-Json]'
    Write-Host '  .\lea.ps1 stop-core'
    Write-Host '  .\lea.ps1 switch-model -ProfileId <id> [-Json]'
    Write-Host '  .\lea.ps1 start-model | stop-model'
}

# Lit uniformément une propriété dans un dictionnaire ou un objet PowerShell.
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

# Écrit uniformément une propriété dans l'état désérialisé.
function Set-ObjectValue {
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

# Retire une propriété d'état sans échouer lorsqu'elle est déjà absente.
function Remove-ObjectValue {
    param(
        [Parameter(Mandatory = $true)]$Object,
        [Parameter(Mandatory = $true)][string]$Name
    )

    if ($Object -is [System.Collections.IDictionary]) {
        [void]$Object.Remove($Name)
        return
    }

    $property = $Object.PSObject.Properties[$Name]
    if ($null -ne $property) {
        [void]$Object.PSObject.Properties.Remove($Name)
    }
}

# Compare deux chemins Windows canoniques sans tenir compte de la casse.
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

# Retourne les PID qui écoutent réellement le port demandé.
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

# Attend brièvement qu'un port libéré par un processus géré disparaisse.
function Wait-ForPortRelease {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )

    $deadline = [datetime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([datetime]::UtcNow -lt $deadline) {
        if (@(Get-ListeningPids -Port $Port).Count -eq 0) {
            return $true
        }

        Start-Sleep -Milliseconds 250
    }

    return @(Get-ListeningPids -Port $Port).Count -eq 0
}

# Bloque un démarrage si un processus inconnu possède déjà le port.
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

# Lit le chemin exécutable d'un PID pour vérifier son identité.
function Get-ProcessPath {
    param([Parameter(Mandatory = $true)][System.Diagnostics.Process]$Process)

    try {
        return $Process.Path
    } catch {
        return $null
    }
}

# Capture les éléments stables nécessaires pour reconnaître un processus plus tard.
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

# Vérifie qu'un record désigne encore le même processus avant toute action.
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

# Crée le répertoire local ignoré qui contient état et journaux d'exécution.
function Initialize-StateDirectory {
    if (-not (Test-Path -LiteralPath $StateDirectory)) {
        New-Item -ItemType Directory -Path $StateDirectory -Force | Out-Null
    }
}

# Relit l'état local et refuse un document corrompu ou étranger au projet.
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

    if ($null -eq (Get-ObjectValue -Object $state -Name 'components')) {
        throw "L’état temporaire de Léa est incomplet. Aucun processus ne sera arrêté automatiquement."
    }

    return $state
}

# Persiste l'état courant dans un JSON lisible par les commandes suivantes.
function Write-LeaState {
    param([Parameter(Mandatory = $true)]$State)

    Initialize-StateDirectory
    $State | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $StateFile -Encoding UTF8
}

# Supprime uniquement l'état devenu vide après arrêt des composants gérés.
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

# Nettoie les anciens journaux connus avant une nouvelle session locale.
function Clear-PreviousLogs {
    Initialize-StateDirectory
    foreach ($fileName in ($KnownStateFiles | Where-Object { $_ -ne 'processes.json' })) {
        $filePath = Join-Path $StateDirectory $fileName
        if (Test-Path -LiteralPath $filePath) {
            Remove-Item -LiteralPath $filePath -Force
        }
    }
}

# Prépare un stdin vide pour empêcher un service caché d'attendre une saisie.
function Ensure-EmptyStandardInputFile {
    Initialize-StateDirectory

    # Les composants déjà gérés peuvent garder ce fichier vide ouvert comme
    # stdin. Le réutiliser lorsqu'il est bien vide évite de le réécrire (et de
    # rompre start-core après stop-core alors que Vite reste actif).
    if (Test-Path -LiteralPath $StandardInputFile) {
        $existingFile = Get-Item -LiteralPath $StandardInputFile -ErrorAction Stop
        if ($existingFile.Length -eq 0) {
            return
        }
    }

    [System.IO.File]::WriteAllBytes($StandardInputFile, [byte[]]@())
}

# Construit un état neuf associé à cette racine de projet.
function New-LeaState {
    return [ordered]@{
        version = 1
        projectRoot = $ProjectRoot
        phase = 'starting'
        components = [ordered]@{}
    }
}

# Retourne la collection de composants en tolérant les anciens états plats.
function Get-StateComponents {
    param([Parameter(Mandatory = $true)]$State)

    $components = Get-ObjectValue -Object $State -Name 'components'
    if ($null -eq $components) {
        throw "L’état temporaire de Léa ne contient pas de composants valides."
    }

    return $components
}

# Enregistre un composant géré sous son nom stable.
function Set-ComponentState {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)][string]$ComponentName,
        [Parameter(Mandatory = $true)]$Value
    )

    Set-ObjectValue -Object (Get-StateComponents -State $State) -Name $ComponentName -Value $Value
}

# Oublie le record d'un composant dont l'arrêt a été confirmé.
function Remove-ComponentState {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)][string]$ComponentName
    )

    Remove-ObjectValue -Object (Get-StateComponents -State $State) -Name $ComponentName
}

# Liste les composants réellement présents dans l'état persistant.
function Get-RecordedComponentNames {
    param([Parameter(Mandatory = $true)]$State)

    $components = Get-StateComponents -State $State
    $recordedNames = @()
    foreach ($componentName in $AllComponentNames) {
        if ($null -ne (Get-ObjectValue -Object $components -Name $componentName)) {
            $recordedNames += $componentName
        }
    }

    return @($recordedNames)
}

# Retrouve le processus principal d'un composant pour les contrôles de propriété.
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

# Vérifie qu'un endpoint local répond avec le contenu minimal attendu.
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

# Attend la disponibilité réelle d'un composant après son lancement.
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

# Confirme que le processus enregistré possède bien son port public.
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

# Arrête un processus lancé pendant la commande si sa préparation échoue.
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

# Lance le profil demandé avec les seuls arguments validés par le registre.
function Start-Model {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)][string]$ProfileId
    )

    $definition = $ComponentDefinitions.model
    $profile = Get-RegistryProfile -Registry $ModelRegistry -ProfileId $ProfileId
    if ([string]$profile.agent_engine -ne 'direct') {
        throw "Le profil $ProfileId doit être démarré par OpenHands, pas par le lanceur llama.cpp Général."
    }
    $modelPath = Resolve-RegistryFile -RelativePath ([string]$profile.model_path) -AllowedRoot (Join-Path $ProjectRoot 'models') -Label "Modèle $ProfileId"
    $modelAlias = [string]$profile.runtime.alias
    $contextSize = [int]$profile.context_tokens
    Assert-PortFree -Port $definition.Port -ComponentLabel $definition.Label
    Write-Host "Démarrage du modèle local $([string]$profile.display_name)..."

    # Tous les paramètres significatifs proviennent du profil central validé.
    $runtime = $profile.runtime
    $arguments = '-m "' + $modelPath + '" -c ' + $contextSize + ' -np ' + [int]$runtime.parallel_slots + ' --host ' + [string]$ModelRegistry.runtime.host + ' --port ' + [int]$ModelRegistry.runtime.port + ' --threads ' + [int]$runtime.threads + ' --batch-size ' + [int]$runtime.batch_size + ' --ubatch-size ' + [int]$runtime.ubatch_size + ' --cache-type-k ' + [string]$runtime.cache_type_k + ' --cache-type-v ' + [string]$runtime.cache_type_v + ' --prio ' + [int]$runtime.priority + ' --alias ' + $modelAlias
    if ([string]$runtime.gpu_layers -ne 'auto') {
        $arguments += ' --gpu-layers ' + [int]$runtime.gpu_layers
    }
    if ([bool]$runtime.jinja) {
        $arguments += ' --jinja'
    }
    if ([bool]$runtime.mmap) {
        $arguments += ' --mmap'
    } else {
        $arguments += ' --no-mmap'
    }
    $arguments += ' --cache-ram ' + $(if ([bool]$runtime.cache_ram) { '1' } else { '0' })
    if (-not [bool]$runtime.skip_chat_parsing) {
        $arguments += ' --no-skip-chat-parsing'
    }
    if ([bool]$runtime.fit) {
        $arguments += ' --fit on --fit-target ' + [int]$runtime.fit_target_mib + ' --fit-ctx ' + [int]$runtime.fit_context_min_tokens
    }
    $process = $null
    try {
        $process = Start-Process -FilePath $ModelExecutable -ArgumentList $arguments -WorkingDirectory $ProjectRoot -PassThru -WindowStyle Hidden -RedirectStandardInput $StandardInputFile -RedirectStandardOutput (Join-Path $StateDirectory 'model.stdout.log') -RedirectStandardError (Join-Path $StateDirectory 'model.stderr.log')
        $resourcePolicyName = [string]$profile.resource_policy
        $resourcePolicy = Get-ObjectValue -Object $ModelRegistry.resource_policies -Name $resourcePolicyName
        if ($null -eq $resourcePolicy) {
            throw "Politique de ressources introuvable : $resourcePolicyName"
        }
        switch ([string]$resourcePolicy.cpu_priority) {
            'idle' { $process.PriorityClass = 'Idle' }
            'below_normal' { $process.PriorityClass = 'BelowNormal' }
            'normal' { $process.PriorityClass = 'Normal' }
            default { throw "Priorité CPU inconnue : $($resourcePolicy.cpu_priority)" }
        }
        $launcherRecord = New-ProcessRecord -ProcessId $process.Id -ExpectedName $definition.ExpectedName -ExpectedPath $definition.ExpectedPath
        Set-ComponentState -State $State -ComponentName 'model' -Value ([ordered]@{
            launcher = $launcherRecord
            listener = $null
            profileId = $ProfileId
        })
        Write-LeaState -State $State
        Wait-ForEndpoint -ComponentLabel $definition.Label -Uri $definition.Endpoint -ExpectedContent $modelAlias -TimeoutSeconds 180
        $listenerPids = @(Get-ListeningPids -Port $definition.Port)
        if ($listenerPids.Count -ne 1) {
            throw "Le modèle n’a pas un PID d’écoute unique sur le port $($definition.Port)."
        }

        Assert-ListenerBelongsToLauncher -ListenerProcessId $listenerPids[0] -LauncherProcessId $process.Id -ComponentLabel $definition.Label
        $listenerRecord = New-ProcessRecord -ProcessId $listenerPids[0] -ExpectedName $definition.ExpectedName -ExpectedPath $definition.ExpectedPath -Port $definition.Port
        $modelState = Get-ObjectValue -Object (Get-StateComponents -State $State) -Name 'model'
        Set-ObjectValue -Object $modelState -Name 'listener' -Value $listenerRecord
        Write-LeaState -State $State
        Assert-RecordOwnsPort -Record $listenerRecord -ComponentLabel $definition.Label
    } catch {
        if ($null -ne $process -and $null -eq (Get-ObjectValue -Object (Get-ObjectValue -Object $State -Name 'components') -Name 'model')) {
            Stop-JustStartedProcess -Process $process
        }

        throw
    }
}

# Démarre FastAPI et enregistre son lanceur ainsi que son écouteur vérifié.
function Start-Backend {
    param([Parameter(Mandatory = $true)]$State)

    $definition = $ComponentDefinitions.backend
    Assert-PortFree -Port $definition.Port -ComponentLabel $definition.Label
    Write-Host 'Démarrage du backend FastAPI...'

    $process = $null
    $previousRegistryPath = [Environment]::GetEnvironmentVariable('LEA_MODEL_REGISTRY', 'Process')
    try {
        try {
            [Environment]::SetEnvironmentVariable('LEA_MODEL_REGISTRY', $ModelRegistryPath, 'Process')
            $process = Start-Process -FilePath $BackendPython -ArgumentList '-m uvicorn app.main:app --host 127.0.0.1 --port 8000' -WorkingDirectory $BackendDirectory -PassThru -WindowStyle Hidden -RedirectStandardInput $StandardInputFile -RedirectStandardOutput (Join-Path $StateDirectory 'backend.stdout.log') -RedirectStandardError (Join-Path $StateDirectory 'backend.stderr.log')
        } finally {
            [Environment]::SetEnvironmentVariable('LEA_MODEL_REGISTRY', $previousRegistryPath, 'Process')
        }
        $launcherRecord = New-ProcessRecord -ProcessId $process.Id -ExpectedName $definition.ExpectedName -ExpectedPath $definition.ExpectedPath
        Set-ComponentState -State $State -ComponentName 'backend' -Value ([ordered]@{
            launcher = $launcherRecord
            listener = $null
        })
        Write-LeaState -State $State
        Wait-ForEndpoint -ComponentLabel $definition.Label -Uri $definition.Endpoint -ExpectedContent $definition.ExpectedContent -TimeoutSeconds 30
        $listenerPids = @(Get-ListeningPids -Port $definition.Port)
        if ($listenerPids.Count -ne 1) {
            throw "Le backend n’a pas un PID d’écoute unique sur le port $($definition.Port)."
        }

        Assert-ListenerBelongsToLauncher -ListenerProcessId $listenerPids[0] -LauncherProcessId $process.Id -ComponentLabel $definition.Label
        $listenerRecord = New-ProcessRecord -ProcessId $listenerPids[0] -ExpectedName $definition.ExpectedName -ExpectedPath $null -Port $definition.Port
        $backendState = Get-ObjectValue -Object (Get-StateComponents -State $State) -Name 'backend'
        Set-ObjectValue -Object $backendState -Name 'listener' -Value $listenerRecord
        Write-LeaState -State $State
        Assert-RecordOwnsPort -Record $listenerRecord -ComponentLabel $definition.Label
    } catch {
        if ($null -ne $process -and $null -eq (Get-ObjectValue -Object (Get-ObjectValue -Object $State -Name 'components') -Name 'backend')) {
            Stop-JustStartedProcess -Process $process
        }

        throw
    }
}

# Démarre Vite sur loopback et conserve l'identité de son processus.
function Start-Frontend {
    param([Parameter(Mandatory = $true)]$State)

    $definition = $ComponentDefinitions.frontend
    Assert-PortFree -Port $definition.Port -ComponentLabel $definition.Label
    Write-Host 'Démarrage du frontend Vite...'

    $npmCommand = (Get-Command npm.cmd -ErrorAction Stop).Source
    $process = $null
    try {
        $process = Start-Process -FilePath $npmCommand -ArgumentList 'run dev -- --host 127.0.0.1 --port 5173' -WorkingDirectory $ProjectRoot -PassThru -WindowStyle Hidden -RedirectStandardInput $StandardInputFile -RedirectStandardOutput (Join-Path $StateDirectory 'frontend.stdout.log') -RedirectStandardError (Join-Path $StateDirectory 'frontend.stderr.log')
        $launcherRecord = New-ProcessRecord -ProcessId $process.Id -ExpectedName $process.ProcessName -ExpectedPath (Get-ProcessPath -Process $process)
        Set-ComponentState -State $State -ComponentName 'frontend' -Value ([ordered]@{
            launcher = $launcherRecord
            listener = $null
        })
        Write-LeaState -State $State
        Wait-ForEndpoint -ComponentLabel $definition.Label -Uri $definition.Endpoint -ExpectedContent $definition.ExpectedContent -TimeoutSeconds 30
        $listenerPids = @(Get-ListeningPids -Port $definition.Port)
        if ($listenerPids.Count -ne 1) {
            throw "Le frontend n’a pas un PID d’écoute unique sur le port $($definition.Port)."
        }

        Assert-ListenerBelongsToLauncher -ListenerProcessId $listenerPids[0] -LauncherProcessId $process.Id -ComponentLabel $definition.Label
        $listenerRecord = New-ProcessRecord -ProcessId $listenerPids[0] -ExpectedName $definition.ExpectedName -ExpectedPath $null -Port $definition.Port
        $frontendState = Get-ObjectValue -Object (Get-StateComponents -State $State) -Name 'frontend'
        Set-ObjectValue -Object $frontendState -Name 'listener' -Value $listenerRecord
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

# Retrouve le profil réellement associé au modèle actuellement enregistré.
function Get-ModelProfileIdFromState {
    # Les anciens états sans profil restent lisibles comme profil Général.
    param($State)

    if ($null -eq $State) {
        return $DefaultProfileId
    }
    $components = Get-ObjectValue -Object $State -Name 'components'
    $modelState = Get-ObjectValue -Object $components -Name 'model'
    $recordedProfileId = Get-ObjectValue -Object $modelState -Name 'profileId'
    if ([string]::IsNullOrWhiteSpace([string]$recordedProfileId)) {
        return $DefaultProfileId
    }
    [void](Get-RegistryProfile -Registry $ModelRegistry -ProfileId ([string]$recordedProfileId))
    return [string]$recordedProfileId
}

# Déduit du registre le contenu de readiness attendu pour chaque composant.
function Get-EndpointExpectedContent {
    # L'alias attendu du modèle suit l'état actif, jamais une constante du frontend.
    param(
        [Parameter(Mandatory = $true)][string]$ComponentName,
        $State
    )

    if ($ComponentName -ne 'model') {
        return $ComponentDefinitions[$ComponentName].ExpectedContent
    }
    $profileId = Get-ModelProfileIdFromState -State $State
    return [string](Get-RegistryProfile -Registry $ModelRegistry -ProfileId $profileId).runtime.alias
}

# Produit un résumé structuré de l'état sans exposer les commandes complètes.
function Get-StateSummary {
    param(
        [Parameter(Mandatory = $true)]$State,
        [string[]]$ComponentNames = $AllComponentNames
    )

    $items = [ordered]@{}
    $allActive = $true
    $allStopped = $true
    $components = Get-StateComponents -State $State

    foreach ($componentName in $ComponentNames) {
        $record = Get-PrimaryRecord -State $State -ComponentName $componentName
        $check = Test-ProcessRecord -Record $record
        $componentState = Get-ObjectValue -Object $components -Name $componentName
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

# Confirme ensemble la propriété des processus et la disponibilité des endpoints.
function Test-AllEndpointsReady {
    param(
        [string[]]$ComponentNames = $AllComponentNames,
        $State
    )

    foreach ($componentName in $ComponentNames) {
        $definition = $ComponentDefinitions[$componentName]
        $expectedContent = Get-EndpointExpectedContent -ComponentName $componentName -State $State
        if (-not (Test-Endpoint -Uri $definition.Endpoint -ExpectedContent $expectedContent)) {
            return $false
        }
    }

    return $true
}

# Interroge le runtime Programmation seulement quand son script officiel existe.
function Get-DevelopmentRuntimeStatus {
    # The Programming model is deliberately not recorded as the direct llama
    # component in lea-state.json. Ask its signed helper instead so status-core
    # can report a healthy mixed core without adopting an unrelated process.
    if (-not (Test-Path -LiteralPath $DevelopmentRuntimeScript -PathType Leaf)) {
        return $null
    }

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $rawStatus = @(& $BackendPython $DevelopmentRuntimeScript status --json 2>$null)
        $helperExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($helperExitCode -ne 0 -or $rawStatus.Count -ne 1) {
        return $null
    }

    try {
        $developmentStatus = ($rawStatus -join "`n") | ConvertFrom-Json -ErrorAction Stop
    } catch {
        return $null
    }

    if ([string]$developmentStatus.state -eq 'ready' -and [string]$developmentStatus.profile_id -eq 'development') {
        return $developmentStatus
    }

    return $null
}

# Retrouve le conteneur Agent Server inactif uniquement s'il appartient à Léa.
function Get-ManagedIdleAgentServer {
    # Inspect only the deterministic idle container and return it only when its
    # labels, image, loopback policy, and state-volume mount still prove ownership.
    $containerName = 'lea-openhands-development-idle'
    $rawInspection = @(& docker.exe container inspect $containerName 2>$null)
    $inspectExitCode = $LASTEXITCODE
    if ($inspectExitCode -ne 0) {
        return $null
    }

    try {
        $container = (($rawInspection -join "`n") | ConvertFrom-Json -ErrorAction Stop)[0]
    } catch {
        throw 'Le conteneur OpenHands idle est illisible; le cœur reste actif.'
    }

    $agentServer = Get-ObjectValue -Object (Get-ObjectValue -Object $ModelRegistry -Name 'openhands') -Name 'agent_server'
    $agentRuntime = Get-ObjectValue -Object (Get-ObjectValue -Object $ModelRegistry -Name 'openhands') -Name 'agent_runtime'
    $labels = Get-ObjectValue -Object (Get-ObjectValue -Object $container -Name 'Config') -Name 'Labels'
    $hostConfig = Get-ObjectValue -Object $container -Name 'HostConfig'
    $mounts = @(Get-ObjectValue -Object $container -Name 'Mounts')
    $stateMounts = @($mounts | Where-Object {
        [string](Get-ObjectValue -Object $_ -Name 'Destination') -eq [string](Get-ObjectValue -Object $agentRuntime -Name 'state_volume_path')
    })
    $projectMounts = @($mounts | Where-Object {
        [string](Get-ObjectValue -Object $_ -Name 'Destination') -eq '/workspace'
    })
    $containerId = [string](Get-ObjectValue -Object $container -Name 'Id')
    $isManaged = (
        $containerId -match '^[0-9a-f]{64}$' -and
        [string](Get-ObjectValue -Object (Get-ObjectValue -Object $container -Name 'Config') -Name 'Image') -eq [string](Get-ObjectValue -Object $agentServer -Name 'image') -and
        [string](Get-ObjectValue -Object $labels -Name 'com.projet-lea.openhands.managed') -eq 'true' -and
        [string](Get-ObjectValue -Object $labels -Name 'com.projet-lea.openhands.mode') -eq 'idle' -and
        [string](Get-ObjectValue -Object $labels -Name 'com.projet-lea.openhands.run-id') -eq '' -and
        -not [bool](Get-ObjectValue -Object $hostConfig -Name 'Privileged') -and
        [string](Get-ObjectValue -Object $hostConfig -Name 'NetworkMode') -ne 'host' -and
        $stateMounts.Count -eq 1 -and
        [string](Get-ObjectValue -Object $stateMounts[0] -Name 'Name') -eq [string](Get-ObjectValue -Object $agentRuntime -Name 'state_volume') -and
        $projectMounts.Count -eq 0 -and
        $mounts.Count -eq 1
    )
    if (-not $isManaged) {
        throw 'Le conteneur OpenHands idle ne correspond plus à la configuration gérée; le cœur reste actif.'
    }

    return $container
}

# Arrête le runtime Programmation vérifié sans toucher aux conteneurs étrangers.
function Stop-ProgrammingRuntime {
    # Stop only the two Programming owners verified by their independent state;
    # an unknown Docker container or Windows process is never adopted or killed.
    $container = Get-ManagedIdleAgentServer
    if ($null -ne $container -and [bool](Get-ObjectValue -Object (Get-ObjectValue -Object $container -Name 'State') -Name 'Running')) {
        & docker.exe container stop --time 30 ([string](Get-ObjectValue -Object $container -Name 'Id')) | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "L'Agent Server OpenHands géré ne peut pas être arrêté en sécurité."
        }
    }

    if (-not (Test-Path -LiteralPath $DevelopmentRuntimeScript -PathType Leaf)) {
        return
    }
    $rawStatus = @(& $BackendPython $DevelopmentRuntimeScript stop --json 2>$null)
    $helperExitCode = $LASTEXITCODE
    if ($helperExitCode -ne 0 -or $rawStatus.Count -ne 1) {
        throw 'Le runtime Qwen Programmation ne peut pas confirmer son arrêt.'
    }
    try {
        $developmentStatus = ($rawStatus -join "`n") | ConvertFrom-Json -ErrorAction Stop
    } catch {
        throw 'Le runtime Qwen Programmation a retourné un état illisible.'
    }
    if ([string]$developmentStatus.state -ne 'stopped') {
        throw 'Le runtime Qwen Programmation reste actif; le cœur reste actif.'
    }
}

# Calcule l'état public du cœur à partir des processus et endpoints réels.
function Get-CoreStatus {
    param($State)

    $componentStates = [ordered]@{}
    $hasError = $false
    $hasStarting = $false
    $readyCount = 0
    $stoppedCount = 0
    $summary = $null

    if ($null -ne $State) {
        $summary = Get-StateSummary -State $State -ComponentNames $CoreComponentNames
    }

    foreach ($componentName in $CoreComponentNames) {
        $definition = $ComponentDefinitions[$componentName]
        $componentStatus = 'stopped'

        if ($null -eq $summary) {
            $owners = @(Get-ListeningPids -Port $definition.Port)
            if ($owners.Count -gt 0) {
                $componentStatus = 'error'
            }
        } else {
            $item = $summary.Items[$componentName]
            if ($item.Check.Exists -and -not $item.Check.Verified) {
                $componentStatus = 'error'
            } elseif ($item.LauncherCheck.Exists -and -not $item.LauncherCheck.Verified) {
                $componentStatus = 'error'
            } elseif ($item.Active -and $item.LauncherCheck.Exists -and $item.LauncherCheck.Verified) {
                $expectedContent = Get-EndpointExpectedContent -ComponentName $componentName -State $State
                if (Test-Endpoint -Uri $definition.Endpoint -ExpectedContent $expectedContent) {
                    $componentStatus = 'ready'
                } else {
                    $componentStatus = 'error'
                }
            } elseif ($item.LauncherCheck.Exists -and $item.LauncherCheck.Verified) {
                $componentStatus = 'starting'
            } elseif ($item.Check.Exists) {
                $componentStatus = 'error'
            } else {
                $owners = @(Get-ListeningPids -Port $definition.Port)
                if ($owners.Count -gt 0) {
                    $componentStatus = 'error'
                }
            }
        }

        $componentStates[$componentName] = $componentStatus
        switch ($componentStatus) {
            'ready' { $readyCount++ }
            'stopped' { $stoppedCount++ }
            'starting' { $hasStarting = $true }
            'error' { $hasError = $true }
        }
    }

    # During Programming the direct General model record is intentionally
    # absent. Count the independently verified Development helper as the model
    # component only when FastAPI is already healthy and no direct error exists.
    $developmentRuntime = $null
    if ($componentStates.model -eq 'stopped' -and $componentStates.backend -eq 'ready') {
        $developmentRuntime = Get-DevelopmentRuntimeStatus
        if ($null -ne $developmentRuntime) {
            $componentStates.model = 'ready'
            $readyCount++
            $stoppedCount--
        }
    }

    $activeProfileId = $null
    if ($null -ne $developmentRuntime) {
        $activeProfileId = 'development'
    } elseif ($null -ne $State -and $null -ne (Get-ObjectValue -Object (Get-StateComponents -State $State) -Name 'model')) {
        $activeProfileId = Get-ModelProfileIdFromState -State $State
    }

    if ($readyCount -eq $CoreComponentNames.Count) {
        $stateName = 'ready'
        $message = 'Léa est prête.'
    } elseif ($stoppedCount -eq $CoreComponentNames.Count) {
        $stateName = 'stopped'
        $message = 'Léa est arrêtée.'
    } elseif ($hasError) {
        $stateName = 'error'
        $message = 'Le cœur de Léa est dans un état incohérent ou un port est occupé par un processus non géré.'
    } elseif ($hasStarting) {
        $stateName = 'starting'
        $message = 'Démarrage du cœur de Léa en cours.'
    } else {
        $stateName = 'error'
        $message = "L’état du cœur de Léa est inconnu."
    }

    return [pscustomobject]@{
        state = $stateName
        model = $componentStates.model
        backend = $componentStates.backend
        active_profile_id = $activeProfileId
        message = $message
    }
}

# Présente l'état des composants dans un format lisible en console.
function Write-LeaStatus {
    param($State)

    Write-Host 'Léa'
    if ($null -eq $State) {
        foreach ($componentName in $AllComponentNames) {
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

    $summary = Get-StateSummary -State $State -ComponentNames $AllComponentNames
    foreach ($componentName in $AllComponentNames) {
        $definition = $ComponentDefinitions[$componentName]
        $item = $summary.Items[$componentName]
        if ($item.Active -and $item.LauncherCheck.Exists -and $item.LauncherCheck.Verified) {
            Write-Host ("{0,-10}: actif (PID {1})" -f $definition.Label, (Get-ObjectValue -Object $item.Record -Name 'pid'))
        } elseif ($item.LauncherCheck.Exists -and $item.LauncherCheck.Verified -and $null -eq $item.Record) {
            Write-Host ("{0,-10}: démarrage en cours" -f $definition.Label)
        } elseif (-not $item.Check.Exists -and -not $item.LauncherCheck.Exists) {
            $owners = @(Get-ListeningPids -Port $definition.Port)
            if ($owners.Count -eq 0) {
                Write-Host ("{0,-10}: arrêté" -f $definition.Label)
            } else {
                Write-Host ("{0,-10}: inconnu (port {1} occupé par PID {2})" -f $definition.Label, $definition.Port, ($owners -join ', '))
            }
        } else {
            Write-Host ("{0,-10}: état incohérent — {1}" -f $definition.Label, $item.Check.Reason)
        }
    }

    if ($summary.AllActive) {
        Write-Host 'Interface : http://127.0.0.1:5173'
    }
}

# Affiche ou sérialise le statut du cœur pour le contrôleur Vite.
function Show-CoreStatus {
    param([switch]$JsonOutput)

    $status = Get-CoreStatus -State (Read-LeaState)
    if ($JsonOutput) {
        $status | ConvertTo-Json -Compress
        return
    }

    Write-Host 'Cœur Léa'
    Write-Host ("Modèle   : {0}" -f $status.model)
    Write-Host ("Backend  : {0}" -f $status.backend)
    Write-Host $status.message
}

# Arrête proprement un processus dont l'identité complète est encore valide.
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

# Termine un record déjà vérifié sans adopter d'autre processus par son port.
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

# Attend que la mémoire GPU du modèle soit effectivement rendue au système.
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

# Arrête les processus enregistrés d'un composant dans un ordre sûr.
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

# Retire de l'état les composants dont tous les records sont maintenant arrêtés.
function Remove-StoppedComponentStates {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)][string[]]$ComponentNames
    )

    $summary = Get-StateSummary -State $State -ComponentNames $ComponentNames
    foreach ($componentName in $ComponentNames) {
        $item = $summary.Items[$componentName]
        if (-not $item.Check.Exists -and -not $item.LauncherCheck.Exists) {
            Remove-ComponentState -State $State -ComponentName $componentName
        }
    }
}

# Coordonne l'arrêt d'un ensemble précis de composants déjà enregistrés.
function Stop-LeaFromState {
    param(
        [Parameter(Mandatory = $true)]$State,
        [string[]]$ComponentNames = $AllComponentNames,
        [switch]$KeepLogs
    )

    $summary = Get-StateSummary -State $State -ComponentNames $ComponentNames
    $ownedComponentNames = @()
    foreach ($componentName in $ComponentNames) {
        $item = $summary.Items[$componentName]
        if ($item.Check.Exists -and -not $item.Check.Verified) {
            $definition = $ComponentDefinitions[$componentName]
            throw "Refus d’arrêter Léa : l’état de $($definition.Label) est ambigu. Aucun processus ne sera tué."
        }

        if ($item.LauncherCheck.Exists -and -not $item.LauncherCheck.Verified) {
            $definition = $ComponentDefinitions[$componentName]
            throw "Refus d’arrêter Léa : l’état du lanceur de $($definition.Label) est ambigu. Aucun processus ne sera tué."
        }

        if ($item.Check.Exists -or $item.LauncherCheck.Exists) {
            $ownedComponentNames += $componentName
        }
    }

    $modelPid = $null
    if ($ComponentNames -contains 'model') {
        $modelRecord = $summary.Items.model.Record
        if ($null -eq $modelRecord) {
            $modelRecord = $summary.Items.model.LauncherRecord
        }
        if ($null -ne $modelRecord) {
            $modelPid = [int](Get-ObjectValue -Object $modelRecord -Name 'pid')
        }
    }

    $stopErrors = @()
    foreach ($componentToStop in @(
            [pscustomobject]@{ Name = 'frontend'; Label = 'frontend Vite' },
            [pscustomobject]@{ Name = 'backend'; Label = 'backend FastAPI' },
            [pscustomobject]@{ Name = 'model'; Label = 'modèle local' }
        )) {
        if ($ComponentNames -notcontains $componentToStop.Name) {
            continue
        }

        $item = $summary.Items[$componentToStop.Name]
        if (-not $item.Check.Exists -and -not $item.LauncherCheck.Exists) {
            continue
        }

        try {
            Stop-ComponentFromState -State $State -ComponentName $componentToStop.Name -ComponentLabel $componentToStop.Label
        } catch {
            $stopErrors += "$($componentToStop.Label) : $($_.Exception.Message)"
        }
    }

    foreach ($componentName in $ownedComponentNames) {
        $definition = $ComponentDefinitions[$componentName]
        if (Wait-ForPortRelease -Port $definition.Port -TimeoutSeconds 10) {
            Write-Host "Port $($definition.Port) libéré."
        } else {
            $owners = @(Get-ListeningPids -Port $definition.Port)
            $portMessage = "Le port $($definition.Port) reste utilisé par le PID $($owners -join ', '). Aucun processus inconnu n’a été arrêté."
            Write-Warning $portMessage
            $stopErrors += $portMessage
        }
    }

    $remainingSummary = Get-StateSummary -State $State -ComponentNames $ComponentNames
    foreach ($componentName in $ComponentNames) {
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

    Remove-StoppedComponentStates -State $State -ComponentNames $ComponentNames
    if (@(Get-RecordedComponentNames -State $State).Count -eq 0) {
        Remove-LeaState -KeepLogs:$KeepLogs
    } else {
        Set-ObjectValue -Object $State -Name 'phase' -Value 'partial'
        Write-LeaState -State $State
    }
}

# Vérifie les exécutables et fichiers configurés avant de lancer quoi que ce soit.
function Assert-RequiredFiles {
    param(
        [string[]]$ComponentNames = $AllComponentNames,
        [string]$ModelProfileId = $DefaultProfileId
    )

    $requiredFiles = @()
    $modelProfile = Get-RegistryProfile -Registry $ModelRegistry -ProfileId $ModelProfileId
    $modelPath = Resolve-RegistryFile -RelativePath ([string]$modelProfile.model_path) -AllowedRoot (Join-Path $ProjectRoot 'models') -Label "Modèle $ModelProfileId"
    if ($ComponentNames -contains 'model') {
        $requiredFiles += [pscustomobject]@{ Description = 'le registre des modèles'; Path = $ModelRegistryPath }
        $requiredFiles += [pscustomobject]@{ Description = 'llama-server.exe'; Path = $ModelExecutable }
        $requiredFiles += [pscustomobject]@{ Description = "le modèle $([string]$modelProfile.display_name)"; Path = $modelPath }
    }

    if ($ComponentNames -contains 'backend') {
        $requiredFiles += [pscustomobject]@{ Description = 'le Python de backend/.venv'; Path = $BackendPython }
    }

    if ($ComponentNames -contains 'frontend') {
        $requiredFiles += [pscustomobject]@{ Description = 'package.json'; Path = $PackageFile }
    }

    foreach ($requiredFile in $requiredFiles) {
        if (-not (Test-Path -LiteralPath $requiredFile.Path -PathType Leaf)) {
            throw "Fichier requis introuvable : $($requiredFile.Path) ($($requiredFile.Description))."
        }
    }

    if ($ComponentNames -contains 'model') {
        $actualSize = (Get-Item -LiteralPath $modelPath).Length
        if ($actualSize -ne [int64]$modelProfile.expected_size_bytes) {
            throw "Taille invalide pour le modèle $ModelProfileId : $actualSize octets."
        }
        $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $modelPath).Hash.ToLowerInvariant()
        if ($actualHash -ne [string]$modelProfile.expected_sha256) {
            throw "SHA-256 invalide pour le modèle $ModelProfileId."
        }
    }

    if ($ComponentNames -contains 'frontend') {
        try {
            Get-Command npm.cmd -ErrorAction Stop | Out-Null
        } catch {
            throw 'npm.cmd est introuvable. Installez Node.js avant de démarrer Léa.'
        }
    }
}

# Détermine les composants absents sans redémarrer ceux qui sont déjà sains.
function Get-ComponentsToStart {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)][string[]]$ComponentNames
    )

    $summary = Get-StateSummary -State $State -ComponentNames $ComponentNames
    $componentsToStart = @()
    foreach ($componentName in $ComponentNames) {
        $item = $summary.Items[$componentName]
        $definition = $ComponentDefinitions[$componentName]

        if ($item.Check.Exists -and -not $item.Check.Verified) {
            throw "L’état de $($definition.Label) est ambigu. Exécutez .\lea.ps1 stop avant un nouveau démarrage."
        }

        if ($item.LauncherCheck.Exists -and -not $item.LauncherCheck.Verified) {
            throw "L’état du lanceur de $($definition.Label) est ambigu. Exécutez .\lea.ps1 stop avant un nouveau démarrage."
        }

        if ($item.Active -and $item.LauncherCheck.Exists -and $item.LauncherCheck.Verified) {
            $expectedContent = Get-EndpointExpectedContent -ComponentName $componentName -State $State
            if (-not (Test-Endpoint -Uri $definition.Endpoint -ExpectedContent $expectedContent)) {
                throw "$($definition.Label) est enregistré comme actif mais son point de contrôle ne répond pas. Exécutez .\lea.ps1 stop avant un nouveau démarrage."
            }

            continue
        }

        if ($item.Check.Exists -or $item.LauncherCheck.Exists) {
            throw "L’état de $($definition.Label) est incomplet. Exécutez .\lea.ps1 stop avant un nouveau démarrage."
        }

        Remove-ComponentState -State $State -ComponentName $componentName
        $componentsToStart += $componentName
    }

    return @($componentsToStart)
}

# Démarre un composant nommé et ajoute son record au même état de session.
function Start-ComponentFromState {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)][string]$ComponentName,
        [string]$ModelProfileId = $DefaultProfileId
    )

    switch ($ComponentName) {
        'model' {
            Start-Model -State $State -ProfileId $ModelProfileId
            return
        }
        'backend' {
            Start-Backend -State $State
            return
        }
        'frontend' {
            Start-Frontend -State $State
            return
        }
        default {
            throw "Composant Léa inconnu : $ComponentName"
        }
    }
}

# Orchestre un démarrage partiel ou complet avec rollback des seuls nouveaux composants.
function Start-LeaComponents {
    param(
        [Parameter(Mandatory = $true)][string[]]$ComponentNames,
        [Parameter(Mandatory = $true)][string]$ReadyMessage,
        [Parameter(Mandatory = $true)][string]$AlreadyStartedMessage,
        [string]$ModelProfileId = $DefaultProfileId
    )

    Assert-RequiredFiles -ComponentNames $ComponentNames -ModelProfileId $ModelProfileId

    $state = Read-LeaState
    if ($null -eq $state) {
        Clear-PreviousLogs
        $state = New-LeaState
        $componentsToStart = @($ComponentNames)
    } else {
        $componentsToStart = @(Get-ComponentsToStart -State $state -ComponentNames $ComponentNames)
        if (@(Get-RecordedComponentNames -State $state).Count -eq 0) {
            Remove-LeaState -KeepLogs
            Clear-PreviousLogs
            $state = New-LeaState
            $componentsToStart = @($ComponentNames)
        } else {
            Write-LeaState -State $state
        }
    }

    if ($componentsToStart.Count -eq 0) {
        Write-Host $AlreadyStartedMessage
        return
    }

    Ensure-EmptyStandardInputFile
    Set-ObjectValue -Object $state -Name 'phase' -Value 'starting'
    Write-LeaState -State $state

    $attemptedComponentNames = @()
    try {
        foreach ($componentName in $componentsToStart) {
            $attemptedComponentNames += $componentName
            Start-ComponentFromState -State $state -ComponentName $componentName -ModelProfileId $ModelProfileId
        }

        $requestedSummary = Get-StateSummary -State $state -ComponentNames $ComponentNames
        if (-not $requestedSummary.AllActive -or -not (Test-AllEndpointsReady -ComponentNames $ComponentNames -State $state)) {
            throw 'Les composants demandés ne sont pas tous prêts après leur démarrage.'
        }

        $allSummary = Get-StateSummary -State $state -ComponentNames $AllComponentNames
        $phase = if ($allSummary.AllActive -and (Test-AllEndpointsReady -ComponentNames $AllComponentNames -State $state)) { 'running' } else { 'partial' }
        Set-ObjectValue -Object $state -Name 'phase' -Value $phase
        Write-LeaState -State $state

        Write-Host ''
        Write-Host $ReadyMessage
        foreach ($componentName in $ComponentNames) {
            Write-Host ("{0,-10}: actif" -f $ComponentDefinitions[$componentName].Label)
        }
        if ($phase -eq 'running') {
            Write-Host 'Interface : http://127.0.0.1:5173'
        }
    } catch {
        $failureMessage = $_.Exception.Message
        Write-Host "Échec du démarrage : $failureMessage" -ForegroundColor Red
        try {
            if ($attemptedComponentNames.Count -gt 0) {
                Stop-LeaFromState -State $state -ComponentNames $attemptedComponentNames -KeepLogs
            }
        } catch {
            $cleanupMessage = $_.Exception.Message
            Write-Warning "Nettoyage incomplet : $cleanupMessage"
            throw "$failureMessage Nettoyage incomplet : l’état et les journaux sont conservés."
        }

        throw $failureMessage
    }
}

# Démarre la pile complète gérée par Léa.
function Start-Lea {
    Start-LeaComponents -ComponentNames $AllComponentNames -ReadyMessage 'Léa est prête.' -AlreadyStartedMessage 'Léa est déjà démarrée.'
}

# Démarre uniquement le modèle et le backend.
function Start-Core {
    Start-LeaComponents -ComponentNames $CoreComponentNames -ReadyMessage 'Le cœur de Léa est prêt.' -AlreadyStartedMessage 'Le cœur de Léa est déjà démarré.'
}

# Affiche l'état complet en réutilisant les contrôles de propriété communs.
function Show-LeaStatus {
    $state = Read-LeaState
    if ($null -ne $state) {
        $summary = Get-StateSummary -State $state -ComponentNames $AllComponentNames
        if ($summary.AllStopped) {
            Remove-LeaState -KeepLogs
            $state = $null
        }
    }

    Write-LeaStatus -State $state
}

# Arrête tous les composants appartenant à la session Léa courante.
function Stop-Lea {
    $state = Read-LeaState
    if ($null -eq $state) {
        Write-Host 'Léa est déjà arrêtée.'
        return
    }

    Stop-ProgrammingRuntime
    Stop-LeaFromState -State $state -ComponentNames $AllComponentNames
    Write-Host 'Léa est arrêtée.'
}

# Arrête le backend et les runtimes modèles tout en laissant Vite intact.
function Stop-Core {
    $state = Read-LeaState
    if ($null -eq $state) {
        Write-Host 'Le cœur de Léa est déjà arrêté.'
        return
    }

    Stop-ProgrammingRuntime
    Stop-LeaFromState -State $state -ComponentNames $CoreComponentNames
    Write-Host 'Le cœur de Léa est arrêté.'
}

# Charge seulement le profil Général pour une transition contrôlée du backend.
function Start-GeneralModelOnly {
    # Restaure seulement le modèle Général dans un cœur déjà lancé ; le
    # contrôleur OpenHands l'utilise après avoir arrêté Qwen vérifié.
    $state = Read-LeaState
    if ($null -eq $state) {
        throw 'Le cœur de Léa doit être démarré avant de restaurer le modèle Général.'
    }
    $general = Get-RegistryProfile -Registry $ModelRegistry -ProfileId $DefaultProfileId
    if ([string]$general.agent_engine -ne 'direct') {
        throw 'Le profil Général doit rester servi par le lanceur llama.cpp local.'
    }
    Start-LeaComponents -ComponentNames @('model') -ModelProfileId $DefaultProfileId -ReadyMessage 'Le modèle Général est prêt.' -AlreadyStartedMessage 'Le modèle Général est déjà prêt.'
}

# Décharge seulement le modèle Général dont le record est vérifié.
function Stop-GeneralModelOnly {
    # Arrête uniquement le PID Général dont l'état signé est encore vérifiable,
    # sans toucher FastAPI ni Vite pendant une commutation de profil.
    $state = Read-LeaState
    if ($null -eq $state) {
        return
    }
    Stop-LeaFromState -State $state -ComponentNames @('model') -KeepLogs
}

# Effectue la bascule atomique entre Général et Programmation avec restauration sur échec.
function Switch-LeaModel {
    # Bascule en série : ancien modèle totalement arrêté avant le nouveau, avec rollback.
    param(
        [Parameter(Mandatory = $true)][string]$TargetProfileId,
        [switch]$JsonOutput
    )

    $targetProfile = Get-RegistryProfile -Registry $ModelRegistry -ProfileId $TargetProfileId
    if (-not [bool]$targetProfile.enabled) {
        throw "Le profil $TargetProfileId est désactivé."
    }
    if ([string]$targetProfile.agent_engine -ne 'direct') {
        throw 'Le profil Programmation est activé par le contrôleur OpenHands de Léa, jamais par switch-model direct.'
    }
    $state = Read-LeaState
    if ($null -eq $state) {
        throw 'Le cœur de Léa doit être démarré avant de changer de profil.'
    }
    $summary = Get-StateSummary -State $state -ComponentNames $CoreComponentNames
    if (-not $summary.AllActive -or -not (Test-AllEndpointsReady -ComponentNames $CoreComponentNames -State $state)) {
        throw 'Le cœur de Léa doit être entièrement prêt avant de changer de profil.'
    }
    try {
        $activity = Invoke-RestMethod -UseBasicParsing -Uri 'http://127.0.0.1:8000/api/runtime/activity' -TimeoutSec 5
    } catch {
        throw 'Le backend ne peut pas confirmer que le changement de profil est sûr.'
    }
    if ([bool]$activity.generation_active -or [bool]$activity.agent_run_active) {
        throw 'Le changement de profil est interdit pendant une génération ou un run agent.'
    }

    $previousProfileId = Get-ModelProfileIdFromState -State $state
    if ($previousProfileId -eq $TargetProfileId) {
        $status = Get-CoreStatus -State $state
        if ($JsonOutput) { $status | ConvertTo-Json -Compress }
        return
    }

    try {
        Assert-RequiredFiles -ComponentNames @('model') -ModelProfileId $TargetProfileId
        Stop-LeaFromState -State $state -ComponentNames @('model') -KeepLogs
        $state = Read-LeaState
        if ($null -eq $state) {
            $state = New-LeaState
        }
        Ensure-EmptyStandardInputFile
        Set-ObjectValue -Object $state -Name 'phase' -Value 'switching'
        Write-LeaState -State $state

        Start-Model -State $state -ProfileId $TargetProfileId
        if (-not (Test-AllEndpointsReady -ComponentNames $CoreComponentNames -State $state)) {
            throw "Le profil $TargetProfileId n'est pas prêt après son démarrage."
        }
        Set-ObjectValue -Object $state -Name 'phase' -Value 'partial'
        Write-LeaState -State $state
    } catch {
        $switchFailure = $_.Exception.Message
        try {
            # Une panne peut arriver pendant l'arrêt lui-même si un processus
            # tiers prend le port libéré. On ne l'adopte jamais et on ne le tue
            # jamais : seuls les PID enregistrés et vérifiés peuvent être arrêtés.
            $rollbackState = Read-LeaState
            if ($null -eq $rollbackState) {
                $rollbackState = New-LeaState
            }

            $rollbackReady = $false
            $rollbackSummary = Get-StateSummary -State $rollbackState -ComponentNames @('model')
            $rollbackItem = $rollbackSummary.Items.model
            if (($rollbackItem.Check.Exists -and -not $rollbackItem.Check.Verified) -or
                ($rollbackItem.LauncherCheck.Exists -and -not $rollbackItem.LauncherCheck.Verified)) {
                throw "L’identité du modèle enregistré est ambiguë."
            }

            if ($rollbackItem.Check.Exists -or $rollbackItem.LauncherCheck.Exists) {
                $recordedProfileId = Get-ModelProfileIdFromState -State $rollbackState
                $expectedAlias = [string](Get-RegistryProfile -Registry $ModelRegistry -ProfileId $previousProfileId).runtime.alias
                if ($recordedProfileId -eq $previousProfileId -and
                    $rollbackItem.Active -and
                    $rollbackItem.LauncherCheck.Exists -and
                    $rollbackItem.LauncherCheck.Verified -and
                    (Test-Endpoint -Uri $ComponentDefinitions.model.Endpoint -ExpectedContent $expectedAlias)) {
                    $rollbackReady = $true
                } else {
                    try {
                        Stop-LeaFromState -State $rollbackState -ComponentNames @('model') -KeepLogs
                    } catch {
                        # Si les PID gérés sont réellement partis, une occupation
                        # étrangère du port est traitée plus bas par attente seule.
                        $afterStopSummary = Get-StateSummary -State $rollbackState -ComponentNames @('model')
                        $afterStopItem = $afterStopSummary.Items.model
                        if ($afterStopItem.Check.Exists -or $afterStopItem.LauncherCheck.Exists) {
                            throw
                        }
                    }
                }
            }

            if (-not $rollbackReady) {
                $rollbackState = Read-LeaState
                if ($null -eq $rollbackState) {
                    $rollbackState = New-LeaState
                } else {
                    $staleSummary = Get-StateSummary -State $rollbackState -ComponentNames @('model')
                    $staleItem = $staleSummary.Items.model
                    if (($staleItem.Check.Exists -and -not $staleItem.Check.Verified) -or
                        ($staleItem.LauncherCheck.Exists -and -not $staleItem.LauncherCheck.Verified)) {
                        throw "L’identité du modèle enregistré est ambiguë."
                    }
                    if ($staleItem.Check.Exists -or $staleItem.LauncherCheck.Exists) {
                        throw "Le modèle enregistré est encore actif après la tentative d’arrêt."
                    }
                    Remove-StoppedComponentStates -State $rollbackState -ComponentNames @('model')
                    Set-ObjectValue -Object $rollbackState -Name 'phase' -Value 'partial'
                    Write-LeaState -State $rollbackState
                }

                if (-not (Wait-ForPortRelease -Port $ComponentDefinitions.model.Port -TimeoutSeconds 20)) {
                    throw "Le port du modèle reste occupé par un processus étranger ; aucun processus inconnu n’a été arrêté."
                }

                Assert-RequiredFiles -ComponentNames @('model') -ModelProfileId $previousProfileId
                Ensure-EmptyStandardInputFile
                Start-Model -State $rollbackState -ProfileId $previousProfileId
                if (-not (Test-AllEndpointsReady -ComponentNames $CoreComponentNames -State $rollbackState)) {
                    throw "Le profil $previousProfileId n'est pas prêt après le rollback."
                }
            }
            Set-ObjectValue -Object $rollbackState -Name 'phase' -Value 'partial'
            Write-LeaState -State $rollbackState
        } catch {
            throw "$switchFailure Rollback vers $previousProfileId impossible : $($_.Exception.Message)"
        }
        $rollbackStatus = Get-CoreStatus -State $rollbackState
        Set-ObjectValue -Object $rollbackStatus -Name 'state' -Value 'rollback'
        Set-ObjectValue -Object $rollbackStatus -Name 'message' -Value "$switchFailure Le profil $previousProfileId a été restauré."
        if ($JsonOutput) {
            $rollbackStatus | ConvertTo-Json -Compress
        } else {
            Write-Host $rollbackStatus.message -ForegroundColor Red
        }
        return
    }

    $status = Get-CoreStatus -State $state
    if ($JsonOutput) {
        $status | ConvertTo-Json -Compress
    } else {
        Write-Host "Profil actif : $([string]$targetProfile.display_name)"
    }
}

try {
    if ([string]::IsNullOrWhiteSpace($Action)) {
        Write-Usage
        exit 1
    }

    switch ($Action.ToLowerInvariant()) {
        'start' {
            Start-Lea
            return
        }
        'status' {
            Show-LeaStatus
            return
        }
        'stop' {
            Stop-Lea
            return
        }
        'start-core' {
            Start-Core
            return
        }
        'status-core' {
            Show-CoreStatus -JsonOutput:$Json
            return
        }
        'stop-core' {
            Stop-Core
            return
        }
        'start-model' {
            Start-GeneralModelOnly
            return
        }
        'stop-model' {
            Stop-GeneralModelOnly
            return
        }
        'switch-model' {
            if ([string]::IsNullOrWhiteSpace($ProfileId)) {
                throw 'Le paramètre -ProfileId est obligatoire pour switch-model.'
            }
            Switch-LeaModel -TargetProfileId $ProfileId -JsonOutput:$Json
            return
        }
        default {
            Write-Usage
            exit 1
        }
    }
} catch {
    if ($Json) {
        [pscustomobject]@{
            state = 'error'
            model = 'error'
            backend = 'error'
            message = $_.Exception.Message
        } | ConvertTo-Json -Compress
    } else {
        Write-Host "Erreur : $($_.Exception.Message)" -ForegroundColor Red
    }

    exit 1
}















