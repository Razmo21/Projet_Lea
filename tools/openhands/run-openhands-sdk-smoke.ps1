[CmdletBinding()]
param(
    # Les essais OpenHands autorises suivent strictement 22K, puis 20K, 18K et 16K seulement si le niveau precedent echoue.
    [ValidateSet(22000, 20000, 18000, 16000)]
    [int]$ContextSize = 22000,
    [ValidateRange(300, 3600)]
    [int]$AgentTimeoutSeconds = 1800,
    # Reinitialise explicitement le seul fixture autorise avant un nouveau run, sans ecrasement implicite.
    [switch]$ResetSmokeFixture
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Charge uniquement le contrat SDK/Agent Server ; les scripts Canvas restent inactifs.
Import-Module -Force (Join-Path $PSScriptRoot 'OpenHands.Sdk.Common.psm1')

# Retourne les chemins exacts du fixture source et du seul projet externe que le smoke est autorise a modifier.
function Get-OpenHandsSdkSmokePaths {
    $config = Get-OpenHandsSdkConfig
    $workspace = Assert-OpenHandsSdkWorkspaceRoot
    $project = [System.IO.Path]::GetFullPath((Join-Path $workspace $config.SmokeProjectName)).TrimEnd([char[]]@('\', '/'))
    $expected = (Join-Path $workspace $config.SmokeProjectName).TrimEnd([char[]]@('\', '/'))
    if (-not [string]::Equals($project, $expected, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Le projet smoke ne reste pas sous L:\IA_WORKSPACE : $project"
    }
    $fixture = Join-Path $PSScriptRoot "fixtures\$($config.SmokeProjectName)"
    return [pscustomobject]@{ Project = $project; Fixture = $fixture }
}

# Calcule les hashes des seuls fichiers connus afin de prouver les lectures et modifications sans parcourir de fichiers personnels.
function Get-OpenHandsSdkSmokeHashes {
    param([Parameter(Mandatory = $true)][string]$ProjectPath)

    $hashes = [ordered]@{}
    foreach ($name in @('pricing.py', 'test_pricing.py', 'README.md')) {
        $path = Join-Path $ProjectPath $name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Le fichier smoke requis est absent : $path"
        }
        $hashes[$name] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    return $hashes
}

# Verifie apres arret du serveur que les deux corrections attendues existent dans le seul fichier que l'agent pouvait modifier.
function Test-OpenHandsSdkSmokePricingCorrection {
    param([Parameter(Mandatory = $true)][string]$ProjectPath)

    $pricingPath = Join-Path $ProjectPath 'pricing.py'
    $content = Get-Content -LiteralPath $pricingPath -Raw -Encoding UTF8
    return [ordered]@{
        discount_formula_correct = $content -match [regex]::Escape('1 - discount_percent / 100')
        receipt_label_correct = $content -match [regex]::Escape('Total for {customer}')
        old_discount_formula_absent = $content -notmatch [regex]::Escape('1 + discount_percent / 100')
        old_receipt_label_absent = $content -notmatch [regex]::Escape('Receipt for {customer}')
    }
}

# Copie seulement les trois fichiers du fixture dans le projet smoke apres un echec memoire de notre propre tentative.
function Restore-OpenHandsSdkSmokeFixture {
    param([Parameter(Mandatory = $true)]$Paths)

    if (-not (Test-Path -LiteralPath $Paths.Fixture -PathType Container)) {
        throw "Le fixture smoke est absent : $($Paths.Fixture)"
    }
    if (-not (Test-Path -LiteralPath $Paths.Project)) {
        New-Item -ItemType Directory -Path $Paths.Project -Force | Out-Null
    }
    $projectItem = Get-Item -LiteralPath $Paths.Project -Force
    if (($projectItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Le projet smoke ne peut pas etre un reparse point : $($Paths.Project)"
    }
    foreach ($name in @('pricing.py', 'test_pricing.py', 'README.md')) {
        Copy-Item -LiteralPath (Join-Path $Paths.Fixture $name) -Destination (Join-Path $Paths.Project $name) -Force
    }
    return Get-OpenHandsSdkSmokeHashes -ProjectPath $Paths.Project
}

# Verifie que l'etat initial est exactement le fixture volontairement rouge, ou le cree une seule fois si absent.
function Assert-OpenHandsSdkSmokeFixture {
    param([Parameter(Mandatory = $true)]$Paths)

    if (-not (Test-Path -LiteralPath $Paths.Project)) {
        return Restore-OpenHandsSdkSmokeFixture -Paths $Paths
    }
    $fixtureHashes = Get-OpenHandsSdkSmokeHashes -ProjectPath $Paths.Fixture
    $projectHashes = Get-OpenHandsSdkSmokeHashes -ProjectPath $Paths.Project
    foreach ($name in $fixtureHashes.Keys) {
        if ($fixtureHashes[$name] -ne $projectHashes[$name]) {
            throw "Le projet smoke existant differe du fixture avant le run : $name. Il ne sera pas ecrase silencieusement."
        }
    }
    return $projectHashes
}

# Execute la suite standard library depuis le projet smoke et retient sa sortie pour une preuve reproductible.
function Invoke-OpenHandsSdkSmokeTests {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectPath,
        [Parameter(Mandatory = $true)][string]$Stage
    )

    Push-Location -LiteralPath $ProjectPath
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # Le fixture est volontairement rouge : un code non nul doit devenir une preuve, pas interrompre le gate.
        $ErrorActionPreference = 'Continue'
        $output = @(& python -m unittest -v 2>&1)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
        Pop-Location
    }
    return [ordered]@{
        stage = $Stage
        exit_code = [int]$exitCode
        output = @($output | ForEach-Object { [string]$_ })
    }
}

# Ajoute des echantillons ressources a l'etat sans ecraser les mesures des autres etapes.
function Set-OpenHandsSdkResourceStage {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)][string]$Stage,
        [Parameter(Mandatory = $true)][object[]]$Samples
    )

    $resources = Get-OpenHandsSdkObjectValue -Object $State -Name 'resources'
    Set-OpenHandsSdkObjectValue -Object $resources -Name $Stage -Value $Samples
    Write-OpenHandsSdkStateAtomically -State $State
}

# Extrait une metrique pagefile CIM des echantillons pour comparer une charge a son niveau de depart.
function Get-OpenHandsSdkPagefileUsageMegabytes {
    param(
        [Parameter(Mandatory = $true)][object[]]$Samples,
        [ValidateSet('allocated_mb', 'used_mb', 'peak_mb')][string]$Metric = 'used_mb'
    )

    return @(
        $Samples |
            ForEach-Object { @(Get-OpenHandsSdkObjectValue -Object $_ -Name 'pagefile') } |
            ForEach-Object { $_ } |
            ForEach-Object { [int](Get-OpenHandsSdkObjectValue -Object $_ -Name $Metric) }
    )
}

# Lit les mesures pagefile echantillonnees pendant le run sans transformer une telemetrie indisponible en echec fonctionnel.
function Get-OpenHandsSdkLivePagefileUsageMegabytes {
    param(
        [Parameter(Mandatory = $true)][string]$ResourcesPath,
        [ValidateSet('allocated_mb', 'current_usage_mb', 'peak_usage_mb')][string]$Metric = 'current_usage_mb'
    )

    if (-not (Test-Path -LiteralPath $ResourcesPath -PathType Leaf)) {
        return @()
    }

    $values = New-Object 'System.Collections.Generic.List[int]'
    foreach ($line in Get-Content -LiteralPath $ResourcesPath -Encoding UTF8) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        try {
            $sample = $line | ConvertFrom-Json -ErrorAction Stop
            $pagefile = Get-OpenHandsSdkObjectValue -Object $sample -Name 'pagefile'
            $items = @(Get-OpenHandsSdkObjectValue -Object $pagefile -Name 'items')
            foreach ($item in $items) {
                $value = Get-OpenHandsSdkObjectValue -Object $item -Name $Metric
                if ($null -ne $value) {
                    $values.Add([int]$value)
                }
            }
        } catch {
            # Un echantillon de telemetrie incomplet reste trace dans son JSONL et ne masque pas les autres mesures.
        }
    }
    return @($values)
}

# Restaure les seules variables de processus du runner pour ne pas modifier durablement l'environnement de l'utilisateur.
function Restore-OpenHandsSdkEnvironment {
    param([Parameter(Mandatory = $true)][hashtable]$Previous)

    foreach ($name in $Previous.Keys) {
        if ($null -eq $Previous[$name]) {
            Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
        } else {
            Set-Item -LiteralPath "Env:$name" -Value $Previous[$name]
        }
    }
}

# Execute une seule tentative de contexte et classe strictement un manque RAM distinct d'un echec fonctionnel.
function Invoke-OpenHandsSdkSmokeAttempt {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)]$Paths,
        [Parameter(Mandatory = $true)][ValidateSet(22000, 20000, 18000, 16000)][int]$ContextSize,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )

    $config = Get-OpenHandsSdkConfig
    $stamp = [datetime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    $prefix = Join-Path $config.LogsRoot "sdk-smoke-$ContextSize-$stamp"
    $attempt = [ordered]@{
        context_size = $ContextSize
        started_at_utc = [datetime]::UtcNow.ToString('o')
        log_prefix = $prefix
        kind = 'functional_failure'
        message = $null
        native_tool_probe = $null
        runner_exit_code = $null
        runner = $null
        before_hashes = $null
        after_hashes = $null
        pricing_correction = $null
        initial_tests = $null
        final_tests = $null
        memory_stages = [ordered]@{}
        available_tools = $null
        pagefile_severe = $false
        pagefile = $null
    }
    $modelStarted = $false
    $agentStarted = $false

    try {
        # Refuse de charger Qwen si la machine est deja sous le seuil critique pendant deux mesures stables.
        $beforeModel = Get-OpenHandsSdkStableResourceSamples -ModelRecord $null
        Set-OpenHandsSdkResourceStage -State $State -Stage "before_qwen_$ContextSize" -Samples $beforeModel
        $beforeModelBarrier = Test-OpenHandsSdkMemoryBarrier -Samples $beforeModel
        $attempt.memory_stages['before_qwen'] = $beforeModelBarrier
        if (-not $beforeModelBarrier.Passed) {
            $attempt.kind = 'memory_insufficient'
            $attempt.message = "RAM critique durable avant chargement Qwen : $([math]::Round($beforeModelBarrier.MinimumAvailableRamBytes / 1GB, 2)) Gio."
            return [pscustomobject]$attempt
        }

        Start-OpenHandsSdkLlamaServer -State $State -ContextSize $ContextSize | Out-Null
        $modelStarted = $true
        $model = Get-OpenHandsSdkObjectValue -Object $State -Name 'model'
        $listener = Get-OpenHandsSdkObjectValue -Object $model -Name 'listener'
        $afterLoad = Get-OpenHandsSdkStableResourceSamples -ModelRecord $listener
        Set-OpenHandsSdkResourceStage -State $State -Stage "after_model_load_$ContextSize" -Samples $afterLoad
        $loadBarrier = Test-OpenHandsSdkMemoryBarrier -Samples $afterLoad
        $attempt.memory_stages['after_model_load'] = $loadBarrier
        if (-not $loadBarrier.Passed) {
            $attempt.kind = 'memory_insufficient'
            $attempt.message = "RAM critique durable apres chargement sous 4 Gio : $([math]::Round($loadBarrier.MinimumAvailableRamBytes / 1GB, 2)) Gio."
            return [pscustomobject]$attempt
        }

        $attempt.native_tool_probe = Invoke-OpenHandsSdkNativeToolProbe
        $afterPrompt = Get-OpenHandsSdkStableResourceSamples -ModelRecord $listener
        Set-OpenHandsSdkResourceStage -State $State -Stage "after_first_prompt_$ContextSize" -Samples $afterPrompt
        $promptBarrier = Test-OpenHandsSdkMemoryBarrier -Samples $afterPrompt
        $attempt.memory_stages['after_first_prompt'] = $promptBarrier
        if (-not $promptBarrier.Passed) {
            $attempt.kind = 'memory_insufficient'
            $attempt.message = "RAM critique durable apres premier prompt sous 4 Gio : $([math]::Round($promptBarrier.MinimumAvailableRamBytes / 1GB, 2)) Gio."
            return [pscustomobject]$attempt
        }

        Start-OpenHandsSdkAgentServer -State $State -ContextSize $ContextSize | Out-Null
        $agentStarted = $true
        $afterAgentStart = Get-OpenHandsSdkStableResourceSamples -ModelRecord $listener -ContainerName $config.AgentContainerName
        Set-OpenHandsSdkResourceStage -State $State -Stage "after_agent_server_start_$ContextSize" -Samples $afterAgentStart
        $agentBarrier = Test-OpenHandsSdkMemoryBarrier -Samples $afterAgentStart
        $attempt.memory_stages['after_agent_server_start'] = $agentBarrier
        $agentRecord = Get-OpenHandsSdkObjectValue -Object $State -Name 'agent_server'
        $attempt.available_tools = @(Get-OpenHandsSdkObjectValue -Object $agentRecord -Name 'available_tools')
        if (-not $agentBarrier.Passed) {
            $attempt.kind = 'memory_insufficient'
            $attempt.message = "RAM critique durable apres Agent Server sous 4 Gio : $([math]::Round($agentBarrier.MinimumAvailableRamBytes / 1GB, 2)) Gio."
            return [pscustomobject]$attempt
        }

        $attempt.before_hashes = Get-OpenHandsSdkSmokeHashes -ProjectPath $Paths.Project
        $previousEnvironment = @{}
        foreach ($name in @('LITELLM_LOCAL_MODEL_COST_MAP', 'CUSTOM_TIKTOKEN_CACHE_DIR', 'TIKTOKEN_CACHE_DIR', 'DATA_GYM_CACHE_DIR', 'OPENHANDS_SUPPRESS_BANNER', 'ALLOW_SHORT_CONTEXT_WINDOWS')) {
            $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        }
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $env:LITELLM_LOCAL_MODEL_COST_MAP = 'True'
            $env:CUSTOM_TIKTOKEN_CACHE_DIR = $config.TiktokenCacheRoot
            # Le SDK hote utilise le cache tiktoken officiel sous ces deux noms et ne doit jamais telecharger pendant le smoke.
            $env:TIKTOKEN_CACHE_DIR = $config.TiktokenCacheRoot
            $env:DATA_GYM_CACHE_DIR = $config.TiktokenCacheRoot
            $env:OPENHANDS_SUPPRESS_BANNER = '1'
            if ($ContextSize -eq 16000) {
                # L'utilisateur a explicitement autorise ce seul essai sous le minimum SDK de 16384.
                $env:ALLOW_SHORT_CONTEXT_WINDOWS = 'true'
            } else {
                Remove-Item -LiteralPath 'Env:ALLOW_SHORT_CONTEXT_WINDOWS' -ErrorAction SilentlyContinue
            }
            # Les sorties non nulles 2/3 du runner sont des classifications attendues, pas une exception PowerShell.
            $ErrorActionPreference = 'Continue'
            $runnerOutput = @(& $config.SdkPython $config.SdkRunner `
                --server-url "http://$($config.AgentHost):$($config.AgentHostPort)" `
                --model-alias $config.ModelAlias `
                --context-size $ContextSize `
                --container-name $config.AgentContainerName `
                --events-path "$prefix.events.jsonl" `
                --resources-path "$prefix.resources.jsonl" `
                --result-path "$prefix.result.json" `
                --timeout-seconds $TimeoutSeconds `
                --normal-free-bytes $config.NormalAvailableRamBytes `
                --acceptable-free-bytes $config.AcceptableAvailableRamBytes `
                --critical-free-bytes $config.CriticalAvailableRamBytes 2>&1)
            $attempt.runner_exit_code = [int]$LASTEXITCODE
            [System.IO.File]::WriteAllLines("$prefix.runner.stdout.log", @($runnerOutput | ForEach-Object { [string]$_ }), (New-Object System.Text.UTF8Encoding($false)))
        } finally {
            $ErrorActionPreference = $previousErrorActionPreference
            Restore-OpenHandsSdkEnvironment -Previous $previousEnvironment
        }
        if (Test-Path -LiteralPath "$prefix.result.json" -PathType Leaf) {
            $attempt.runner = Get-Content -LiteralPath "$prefix.result.json" -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop
        } else {
            $attempt.message = 'Le runner SDK a termine sans produire son resultat atomique.'
            return [pscustomobject]$attempt
        }
        # Un timeout ou une interruption ne laisse jamais l'agent continuer pendant les hashes/tests : stop immediat du conteneur connu.
        $interruptionReason = [string](Get-OpenHandsSdkObjectValue -Object $attempt.runner -Name 'interruption_reason')
        $stopImmediately = $attempt.runner_exit_code -ne 0 -or -not [string]::IsNullOrWhiteSpace($interruptionReason)
        $stoppedImmediatelyAfterInterruption = $false
        if ($stopImmediately -and $agentStarted) {
            Stop-OpenHandsSdkAgentServer -State $State
            $agentStarted = $false
            $stoppedImmediatelyAfterInterruption = $true
        }

        # Prend le dernier snapshot, puis inspecte le contrat via l'API exportee du module (pas via une fonction interne).
        $afterRun = @((Get-OpenHandsSdkResourceSnapshot -ModelRecord $listener -ContainerName $config.AgentContainerName))
        Set-OpenHandsSdkResourceStage -State $State -Stage "after_agent_run_$ContextSize" -Samples $afterRun
        $runBarrier = Test-OpenHandsSdkMemoryBarrier -Samples $afterRun
        $attempt.memory_stages['after_agent_run'] = $runBarrier
        $sdkStatus = Get-OpenHandsSdkStatus
        $agentContract = Get-OpenHandsSdkObjectValue -Object $sdkStatus -Name 'agent_server'
        $agentContainer = Get-OpenHandsSdkObjectValue -Object $agentContract -Name 'Container'
        $agentContainerState = Get-OpenHandsSdkObjectValue -Object $agentContainer -Name 'State'
        $attempt.agent_before_stop = [ordered]@{
            healthy = $false
            running = if ($null -eq $agentContainerState) { $false } else { [bool](Get-OpenHandsSdkObjectValue -Object $agentContainerState -Name 'Running') }
            oom_killed = if ($null -eq $agentContainerState) { $null } else { [bool](Get-OpenHandsSdkObjectValue -Object $agentContainerState -Name 'OOMKilled') }
            model_alive = $null -ne (Get-OpenHandsSdkObjectValue -Object $afterRun[0] -Name 'model')
            stopped_immediately_after_interruption = $stoppedImmediatelyAfterInterruption
        }
        if ($stoppedImmediatelyAfterInterruption) {
            $attempt.agent_before_stop['health_error'] = 'Agent Server arrete immediatement apres interruption ou echec runner; aucune validation du bind mount ne precede cet arret.'
        } else {
            try {
                $health = Invoke-WebRequest -Uri "http://$($config.AgentHost):$($config.AgentHostPort)/health" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
                $attempt.agent_before_stop['healthy'] = $health.StatusCode -ge 200 -and $health.StatusCode -lt 300
            } catch { $attempt.agent_before_stop['health_error'] = $_.Exception.Message }
        }
        if ($agentStarted) {
            Stop-OpenHandsSdkAgentServer -State $State
            $agentStarted = $false
        }
        $runnerMinimum = Get-OpenHandsSdkObjectValue -Object $attempt.runner -Name 'minimum_available_ram_bytes'
        $attempt.runner_minimum_available_ram_bytes = $runnerMinimum
        $attempt.minimum_viable_available_ram_bytes = $config.AcceptableAvailableRamBytes
        if ([bool](Get-OpenHandsSdkObjectValue -Object $attempt.runner -Name 'memory_breach') -or ($null -ne $runnerMinimum -and [int64]$runnerMinimum -lt $config.CriticalAvailableRamBytes) -or -not $runBarrier.Passed) {
            $attempt.kind = 'memory_insufficient'
            $attempt.message = 'La marge RAM est descendue durablement sous 4 Gio pendant le vrai run agentique.'
            return [pscustomobject]$attempt
        }

        $resources = Get-OpenHandsSdkObjectValue -Object $State -Name 'resources'
        $baselineSamples = @((Get-OpenHandsSdkObjectValue -Object $resources -Name 'before_qwen'))
        $baselinePagefileUsage = @(Get-OpenHandsSdkPagefileUsageMegabytes -Samples $baselineSamples)
        $afterRunPagefileUsage = @(Get-OpenHandsSdkPagefileUsageMegabytes -Samples $afterRun)
        $livePagefileUsage = @(Get-OpenHandsSdkLivePagefileUsageMegabytes -ResourcesPath "$prefix.resources.jsonl")
        $attemptPagefileUsage = @($afterRunPagefileUsage + $livePagefileUsage)
        $baselinePagefilePeaks = @(Get-OpenHandsSdkPagefileUsageMegabytes -Samples $baselineSamples -Metric 'peak_mb')
        $afterRunPagefilePeaks = @(Get-OpenHandsSdkPagefileUsageMegabytes -Samples $afterRun -Metric 'peak_mb')
        $livePagefilePeaks = @(Get-OpenHandsSdkLivePagefileUsageMegabytes -ResourcesPath "$prefix.resources.jsonl" -Metric 'peak_usage_mb')
        $attemptPagefilePeaks = @($afterRunPagefilePeaks + $livePagefilePeaks)
        $afterRunPagefileAllocated = @(Get-OpenHandsSdkPagefileUsageMegabytes -Samples $afterRun -Metric 'allocated_mb')
        $livePagefileAllocated = @(Get-OpenHandsSdkLivePagefileUsageMegabytes -ResourcesPath "$prefix.resources.jsonl" -Metric 'allocated_mb')
        $attemptPagefileAllocated = @($afterRunPagefileAllocated + $livePagefileAllocated)
        $baselinePagefileMaximum = if ($baselinePagefileUsage.Count -gt 0) { [int](($baselinePagefileUsage | Measure-Object -Maximum).Maximum) } else { $null }
        $attemptPagefileMaximum = if ($attemptPagefileUsage.Count -gt 0) { [int](($attemptPagefileUsage | Measure-Object -Maximum).Maximum) } else { $null }
        $baselinePagefilePeakMaximum = if ($baselinePagefilePeaks.Count -gt 0) { [int](($baselinePagefilePeaks | Measure-Object -Maximum).Maximum) } else { $null }
        $attemptPagefilePeakMaximum = if ($attemptPagefilePeaks.Count -gt 0) { [int](($attemptPagefilePeaks | Measure-Object -Maximum).Maximum) } else { $null }
        $attemptPagefileAllocatedMaximum = if ($attemptPagefileAllocated.Count -gt 0) { [int](($attemptPagefileAllocated | Measure-Object -Maximum).Maximum) } else { $null }
        $pagefileIncrease = if ($null -ne $baselinePagefileMaximum -and $null -ne $attemptPagefileMaximum) { $attemptPagefileMaximum - $baselinePagefileMaximum } else { $null }
        $pagefilePeakIncrease = if ($null -ne $baselinePagefilePeakMaximum -and $null -ne $attemptPagefilePeakMaximum) { $attemptPagefilePeakMaximum - $baselinePagefilePeakMaximum } else { $null }
        $pagefileUsagePercent = if ($null -ne $attemptPagefileMaximum -and $null -ne $attemptPagefileAllocatedMaximum -and $attemptPagefileAllocatedMaximum -gt 0) { [math]::Round((100.0 * $attemptPagefileMaximum) / $attemptPagefileAllocatedMaximum, 1) } else { $null }
        $pagefileSevereUsagePercent = 85.0
        $pagefilePeakGrowthThresholdMb = 1024
        # CurrentUsage peut monter lorsque Windows deplace des pages inactives alors que la RAM physique reste saine.
        # Le smoke ne qualifie donc une pagination de severe que pres de la capacite du pagefile, ou si un nouveau pic
        # d'au moins 1 Gio coincide avec une marge physique critique deja mesuree par la barriere du vrai run.
        $pagefileNearCapacity = $null -ne $pagefileUsagePercent -and $pagefileUsagePercent -ge $pagefileSevereUsagePercent
        $pagefilePeakGrowthUnderCriticalRam = $null -ne $pagefilePeakIncrease -and $pagefilePeakIncrease -ge $pagefilePeakGrowthThresholdMb -and [int64]$runBarrier.MinimumAvailableRamBytes -lt $config.CriticalAvailableRamBytes
        $attempt.pagefile = [ordered]@{
            baseline_max_used_mb = $baselinePagefileMaximum
            after_run_max_used_mb = $attemptPagefileMaximum
            live_sample_count = $livePagefileUsage.Count
            live_max_used_mb = if ($livePagefileUsage.Count -gt 0) { [int](($livePagefileUsage | Measure-Object -Maximum).Maximum) } else { $null }
            live_max_peak_mb = if ($livePagefilePeaks.Count -gt 0) { [int](($livePagefilePeaks | Measure-Object -Maximum).Maximum) } else { $null }
            live_telemetry_available = $livePagefileUsage.Count -gt 0
            current_increase_mb = $pagefileIncrease
            baseline_max_peak_mb = $baselinePagefilePeakMaximum
            after_run_max_peak_mb = $attemptPagefilePeakMaximum
            peak_increase_mb = $pagefilePeakIncrease
            max_allocated_mb = $attemptPagefileAllocatedMaximum
            max_usage_percent = $pagefileUsagePercent
            severe_usage_percent_threshold = $pagefileSevereUsagePercent
            peak_growth_threshold_mb = $pagefilePeakGrowthThresholdMb
            current_increase_is_telemetry_only = $true
        }
        if ($pagefileNearCapacity -or $pagefilePeakGrowthUnderCriticalRam) {
            $attempt.pagefile_severe = $true
        }

        # Le conteneur est maintenant confirme arrete : les hashes et tests host ne peuvent plus courir avec une mutation agent en cours.
        $attempt.after_hashes = Get-OpenHandsSdkSmokeHashes -ProjectPath $Paths.Project
        $attempt.pricing_correction = Test-OpenHandsSdkSmokePricingCorrection -ProjectPath $Paths.Project
        $attempt.final_tests = Invoke-OpenHandsSdkSmokeTests -ProjectPath $Paths.Project -Stage "after_agent_$ContextSize"

        $evidence = Get-OpenHandsSdkObjectValue -Object $attempt.runner -Name 'evidence'
        $changedPricing = [string]$attempt.before_hashes['pricing.py'] -ne [string]$attempt.after_hashes['pricing.py']
        $changedTests = [string]$attempt.before_hashes['test_pricing.py'] -ne [string]$attempt.after_hashes['test_pricing.py']
        $changedReadme = [string]$attempt.before_hashes['README.md'] -ne [string]$attempt.after_hashes['README.md']
        $pricingCorrectionConfirmed = [bool]$attempt.pricing_correction['discount_formula_correct'] -and [bool]$attempt.pricing_correction['receipt_label_correct'] -and [bool]$attempt.pricing_correction['old_discount_formula_absent'] -and [bool]$attempt.pricing_correction['old_receipt_label_absent']
        $toolsUsed = [int](Get-OpenHandsSdkObjectValue -Object $evidence -Name 'project_tool_action_count') -gt 0
        $authoritativeHistory = [int](Get-OpenHandsSdkObjectValue -Object $evidence -Name 'authoritative_history_event_count') -gt 0 -and [string]::IsNullOrWhiteSpace([string](Get-OpenHandsSdkObjectValue -Object $evidence -Name 'history_sync_error'))
        $readFiles = [bool](Get-OpenHandsSdkObjectValue -Object $evidence -Name 'all_required_files_read_before_red_test')
        $redTestObserved = [bool](Get-OpenHandsSdkObjectValue -Object $evidence -Name 'red_unittest_observed')
        $greenTestObserved = [bool](Get-OpenHandsSdkObjectValue -Object $evidence -Name 'green_unittest_observed_after_red')
        $pricingActionBetweenTests = [bool](Get-OpenHandsSdkObjectValue -Object $evidence -Name 'pricing_action_between_red_and_green')
        $orderedSequence = [bool](Get-OpenHandsSdkObjectValue -Object $evidence -Name 'ordered_smoke_sequence_observed')
        $agentSummary = [string](Get-OpenHandsSdkObjectValue -Object $evidence -Name 'agent_summary')
        $noMajorToolError = @((Get-OpenHandsSdkObjectValue -Object $evidence -Name 'major_error_events')).Count -eq 0
        $agentFinished = [string](Get-OpenHandsSdkObjectValue -Object $attempt.runner -Name 'terminal_status') -eq 'finished'
        $interrupted = -not [string]::IsNullOrWhiteSpace([string](Get-OpenHandsSdkObjectValue -Object $attempt.runner -Name 'interruption_reason'))
        $agentHealthy = [bool]$attempt.agent_before_stop['healthy']
        $agentOomFree = -not [bool]$attempt.agent_before_stop['oom_killed']
        $memoryReviewRequired = @($attempt.memory_stages.Values | Where-Object { [bool]$_.RequiresUserReview }).Count -gt 0
        # Un OOM Agent Server ou une hausse severe du pagefile est un manque de ressources, jamais une panne logique a masquer.
        $resourceInstability = -not $agentOomFree -or $attempt.pagefile_severe
        # Le verdict depend exclusivement de l'historique Agent Server, des hashes apres arret et des tests host isoles.
        $functionalEvidenceSatisfied = $attempt.runner_exit_code -eq 0 -and $agentFinished -and -not $interrupted -and $authoritativeHistory -and $toolsUsed -and $readFiles -and $redTestObserved -and $pricingActionBetweenTests -and $greenTestObserved -and $orderedSequence -and $changedPricing -and -not $changedTests -and -not $changedReadme -and $pricingCorrectionConfirmed -and $attempt.final_tests.exit_code -eq 0 -and -not [string]::IsNullOrWhiteSpace($agentSummary) -and $noMajorToolError -and $agentHealthy -and $agentOomFree -and -not $attempt.pagefile_severe
        $runnerBelowViable = $null -eq $runnerMinimum -or [int64]$runnerMinimum -lt $config.AcceptableAvailableRamBytes
        $attempt.ram_viable = -not $memoryReviewRequired -and -not $runnerBelowViable
        if ($resourceInstability) {
            $attempt.kind = 'memory_insufficient'
            $attempt.message = if (-not $agentOomFree) {
                'Le smoke a rencontre un OOM Agent Server ; aucun contexte inferieur ne doit etre evalue comme un echec fonctionnel.'
            } else {
                'Le smoke a declenche une hausse severe du pagefile ; la configuration est instable a ce contexte.'
            }
        } elseif ($functionalEvidenceSatisfied -and $attempt.ram_viable) {
            $attempt.kind = 'success'
            $attempt.message = 'Le smoke SDK/Agent Server a lu, teste, modifie et reteste le projet avec Qwen local.'
        } elseif ($functionalEvidenceSatisfied -and -not $attempt.ram_viable) {
            $attempt.kind = 'memory_insufficient'
            $attempt.message = if ($null -eq $runnerMinimum) {
                'Le smoke est fonctionnel, mais aucune RAM minimale exploitable n a ete mesuree pendant le vrai run.'
            } else {
                "Le smoke est fonctionnel, mais la RAM minimale de $([math]::Round([int64]$runnerMinimum / 1GB, 2)) Gio est sous le seuil viable de $([math]::Round($config.AcceptableAvailableRamBytes / 1GB, 2)) Gio."
            }
        } else {
            $attempt.kind = 'functional_failure'
            $attempt.message = 'Le smoke agentique n a pas satisfait toutes les preuves de lecture, outils, modification, tests verts ou resume.'
        }
        return [pscustomobject]$attempt
    } catch {
        $snapshot = $null
        try {
            $model = Get-OpenHandsSdkObjectValue -Object $State -Name 'model'
            $snapshot = Get-OpenHandsSdkResourceSnapshot -ModelRecord (Get-OpenHandsSdkObjectValue -Object $model -Name 'listener') -ContainerName $(if ($agentStarted) { $config.AgentContainerName } else { $null })
        } catch { $snapshot = $null }
        if ($null -ne $snapshot -and [int64](Get-OpenHandsSdkObjectValue -Object $snapshot -Name 'system_available_ram_bytes') -lt $config.CriticalAvailableRamBytes) {
            $attempt.kind = 'memory_insufficient'
        }
        $attempt.message = $_.Exception.Message
        return [pscustomobject]$attempt
    } finally {
        if ($agentStarted) {
            try { Stop-OpenHandsSdkAgentServer -State $State } catch { Write-Warning $_.Exception.Message }
        }
        if ($modelStarted) {
            try { Stop-OpenHandsSdkLlamaServer -State $State } catch { Write-Warning $_.Exception.Message }
        }
        Set-OpenHandsSdkPhase -State $State -Phase 'stopped'
        Write-OpenHandsSdkStateAtomically -State $State
    }
}

$config = Get-OpenHandsSdkConfig
$state = Read-OpenHandsSdkState
if ($null -eq $state) {
    # L'etat v2 est neuf : il ne reference ni conversations ni volume de l'essai historique CamelCase.
    $state = New-OpenHandsSdkState -ContextSize $ContextSize
    Set-OpenHandsSdkObjectValue -Object $state -Name 'smoke_state_isolation' -Value ([ordered]@{
        generation = 'smoke-v2'
        created_at_utc = [datetime]::UtcNow.ToString('o')
        legacy_state_file = (Join-Path $config.ProjectRoot '.lea\openhands-sdk\bootstrap-state.json')
        legacy_container_name = 'lea-openhands-sdk'
        legacy_state_volume = 'lea_openhands_sdk_state'
        reason = 'Les conversations de test TerminalTool/FileEditorTool/TaskTrackerTool restent preservees et non adoptees.'
    })
}
Set-OpenHandsSdkObjectValue -Object $state -Name 'selected_context' -Value $ContextSize

$paths = Get-OpenHandsSdkSmokePaths
if ($ResetSmokeFixture) {
    # Cette voie est volontairement separee du smoke : elle ne lance ni Docker ni Qwen et ne touche qu'aux trois fichiers connus.
    $resetHashes = Restore-OpenHandsSdkSmokeFixture -Paths $paths
    $resetTests = Invoke-OpenHandsSdkSmokeTests -ProjectPath $paths.Project -Stage 'after_explicit_fixture_reset'
    if ($resetTests.exit_code -eq 0) {
        throw 'Le fixture reinitialise doit rester volontairement rouge avant un vrai run agentique.'
    }
    [pscustomobject]@{
        verdict = 'OPENHANDS_SMOKE_FIXTURE_RESET'
        smoke_project = $paths.Project
        hashes = $resetHashes
        tests = $resetTests
    } | ConvertTo-Json -Depth 10
    exit 0
}

# Effectue le preflight avant toute ecriture dans IA_WORKSPACE, lancement de modele ou creation Docker.
Assert-OpenHandsSdkDockerReady | Out-Null
Assert-OpenHandsSdkModelAndRuntime | Out-Null
$initialHashes = Assert-OpenHandsSdkSmokeFixture -Paths $paths
$initialTests = Invoke-OpenHandsSdkSmokeTests -ProjectPath $paths.Project -Stage 'before_agent'
if ($initialTests.exit_code -eq 0) {
    throw 'Le fixture smoke doit etre rouge avant le vrai agent ; aucun correctif manuel ne sera applique.'
}
$resources = Get-OpenHandsSdkObjectValue -Object $state -Name 'resources'
Set-OpenHandsSdkObjectValue -Object $resources -Name 'before_qwen' -Value @((Get-OpenHandsSdkResourceSnapshot -ModelRecord $null))
Write-OpenHandsSdkStateAtomically -State $state

$attempts = @()
$previousAttempts = Get-OpenHandsSdkObjectValue -Object $state -Name 'attempts'
if ($null -ne $previousAttempts) {
    # Preserve les tentatives precedentes dans le checkpoint au lieu de perdre leur trace au prochain run.
    $attempts += @($previousAttempts)
}
$finalVerdict = 'OPENHANDS_LOCAL_BLOCKED'
$finalMessage = $null
$attempt = Invoke-OpenHandsSdkSmokeAttempt -State $state -Paths $paths -ContextSize $ContextSize -TimeoutSeconds $AgentTimeoutSeconds
$attempts += $attempt
Set-OpenHandsSdkObjectValue -Object $state -Name 'attempts' -Value $attempts
Write-OpenHandsSdkStateAtomically -State $state
if ($attempt.kind -eq 'success') {
    $finalVerdict = 'OPENHANDS_LOCAL_READY'
    $finalMessage = $attempt.message
} elseif ($attempt.kind -eq 'memory_insufficient') {
    $finalMessage = "Marge RAM insuffisante a $ContextSize : $($attempt.message)"
} else {
    $finalMessage = "Echec fonctionnel a $ContextSize : $($attempt.message)"
}

Set-OpenHandsSdkObjectValue -Object $state -Name 'result' -Value ([ordered]@{
    verdict = $finalVerdict
    message = $finalMessage
    completed_at_utc = [datetime]::UtcNow.ToString('o')
    smoke_project = $paths.Project
    initial_hashes = $initialHashes
    initial_tests = $initialTests
})
Set-OpenHandsSdkPhase -State $state -Phase 'stopped' -Failure $(if ($finalVerdict -eq 'OPENHANDS_LOCAL_READY') { $null } else { $finalMessage })
Write-OpenHandsSdkStateAtomically -State $state

[pscustomobject]@{
    verdict = $finalVerdict
    message = $finalMessage
    attempts = $attempts
    state_file = $config.StateFile
    smoke_project = $paths.Project
} | ConvertTo-Json -Depth 30

if ($finalVerdict -ne 'OPENHANDS_LOCAL_READY') {
    exit 1
}
