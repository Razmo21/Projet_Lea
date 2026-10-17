# Essai destructif limité au backend de test : jamais à la base utilisateur.
# Prérequis : LEA_DB_PATH isolé, Programmation prêt, aucun autre run actif.
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$stage13Project = 'L:\IA_WORKSPACE\Lea_Stage13_20261017'
$stage13Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$stage13Database = Join-Path $stage13Root '.test-runtime\stage13-20261017\lea.sqlite3'
if ($env:LEA_DB_PATH -ne $stage13Database) { throw 'La base isolée doit être explicitement sélectionnée.' }
$projectItem = Get-Item -LiteralPath $stage13Project
if ($projectItem.FullName -ne $stage13Project -or ($projectItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw 'Le projet jetable ne correspond pas au chemin autorisé.'
}
$activeRuns = (Invoke-RestMethod http://127.0.0.1:8000/api/agent-runs).runs | Where-Object state -in @('pending', 'running', 'waiting_for_tool')
if ($activeRuns) { throw 'Un run existe déjà ; aucune interruption concurrente.' }
$project = (Invoke-RestMethod http://127.0.0.1:8000/api/projects).projects | Where-Object relative_path -eq 'Lea_Stage13_20261017'
if (-not $project) { throw 'Projet de test absent.' }
# Les UUID du catalogue isolé doivent correspondre à ceux du backend cible.
# Un LEA_DB_PATH défini dans ce shell ne prouve pas l'environnement d'un serveur déjà lancé.
& (Join-Path $stage13Root 'backend\.venv\Scripts\python.exe') -B -c "import sqlite3,sys; c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True); row=c.execute('select id from projects where relative_path=?',('Lea_Stage13_20261017',)).fetchone(); sys.exit(0 if row and row[0]==sys.argv[2] else 1)" $stage13Database $project.id
if ($LASTEXITCODE -ne 0) { throw 'Le backend ne correspond pas au catalogue de la base isolée.' }
$backendPid = (Get-NetTCPConnection -State Listen -LocalAddress 127.0.0.1 -LocalPort 8000).OwningProcess
$backendInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$backendPid"
if ($backendInfo.Name -ne 'python.exe' -or $backendInfo.CommandLine -notlike '*-m uvicorn app.main:app --host 127.0.0.1 --port 8000*') {
    throw 'Le processus backend ne peut pas être identifié.'
}
$backendProcess = Get-Process -Id $backendPid
$backendStarted = $backendProcess.StartTime
# Réinitialisation de la seule source de la fixture, après l'Accept du premier essai.
Copy-Item -LiteralPath (Join-Path $stage13Root 'tools\openhands\fixtures\stage10-python\calculator.py') -Destination (Join-Path $stage13Project 'calculator.py')
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/projects/$($project.id)/activate" | Out-Null
$task = 'Lis README.md, calculator.py et test_calculator.py. Corrige uniquement calculator.py pour que add additionne ses deux arguments. Ne modifie aucun test. Lance python -B -m unittest -v puis termine.'
$run = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/agent-runs -ContentType application/json -Body (@{task=$task} | ConvertTo-Json) -TimeoutSec 180
Write-Output "Run de panne contrôlée : $($run.run_id)"
$deadline = [DateTime]::UtcNow.AddMinutes(4)
while ([DateTime]::UtcNow -lt $deadline) {
    $source = Get-Content -LiteralPath (Join-Path $stage13Project 'calculator.py') -Raw
    if ($source.Contains('return left + right')) {
        $current = Invoke-RestMethod "http://127.0.0.1:8000/api/agent-runs/$($run.run_id)"
        if ($current.state -notin @('running', 'waiting_for_tool')) { throw 'Run déjà terminé ; aucune coupure.' }
        $owned = Get-Process -Id $backendPid
        if ($owned.StartTime -ne $backendStarted) { throw 'Identité du backend modifiée.' }
        $owned.Kill()
        Write-Output "Backend de test interrompu après mutation ; run $($run.run_id), checkpoint $($run.checkpoint_id)."
        exit 0
    }
    Start-Sleep -Milliseconds 250
}
throw 'Aucune mutation observée ; aucun processus arbitrairement interrompu.'
