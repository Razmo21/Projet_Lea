# Installation administrative explicite ; jamais appelée au démarrage de Léa.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$voiceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$runtimeRoot = Join-Path $voiceRoot 'runtime\voice'
$weightsRoot = Join-Path $voiceRoot 'models\voice'
$downloadRoot = Join-Path $runtimeRoot 'downloads'
New-Item -ItemType Directory -Force -Path $downloadRoot,$weightsRoot | Out-Null

function Get-VerifiedVoiceFile {
    # Refuse d'écraser un fichier existant différent et vérifie chaque binaire.
    param([string]$Url, [string]$Destination, [string]$Sha256)
    if (-not (Test-Path -LiteralPath $Destination)) {
        & curl.exe --fail --location --silent --show-error --max-time 900 --output $Destination $Url
        if ($LASTEXITCODE -ne 0) { throw "Téléchargement interrompu : $Destination" }
    }
    if ((Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Sha256) {
        throw "Empreinte incorrecte : $Destination. Aucun lancement autorisé."
    }
    Write-Output "Vérifié : $Destination"
}

$archive = Join-Path $downloadRoot 'whisper-bin-x64.zip'
Get-VerifiedVoiceFile 'https://github.com/ggml-org/whisper.cpp/releases/download/b5130/whisper-bin-x64.zip' $archive 'f9ec6c52a2e949b62ab51fa21d0d497958f9e41c3010c157c4e42932d5316f3c'
Get-VerifiedVoiceFile 'https://huggingface.co/ggerganov/whisper.cpp/resolve/5359861c739e955e79d9a303bcbc70fb988958b1/ggml-small-q5_1.bin' (Join-Path $weightsRoot 'ggml-small-q5_1.bin') 'ae85e4a935d7a567bd102fe55afc16bb595bdb618e11b2fc7591bc08120411bb'
Get-VerifiedVoiceFile 'https://huggingface.co/rhasspy/piper-voices/resolve/c10ece1aade47bb51c153c893d14e5bf8e5b7117/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx' (Join-Path $weightsRoot 'fr_FR-siwis-medium.onnx') '641d1ab097da2b81128c076810edb052b385decc8be3381814802a64a73baf99'

# L'archive vérifiée est extraite dans son dossier dédié, jamais par-dessus llama.cpp.
$whisperRoot = Join-Path $runtimeRoot 'whisper.cpp'
if (-not (Test-Path -LiteralPath $whisperRoot)) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($archive)
    try {
        foreach ($entry in $zip.Entries) {
            $target = [IO.Path]::GetFullPath((Join-Path $whisperRoot $entry.FullName))
            if (-not $target.StartsWith($whisperRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Archive hors périmètre' }
        }
    } finally { $zip.Dispose() }
    Expand-Archive -LiteralPath $archive -DestinationPath $whisperRoot
}

foreach ($name in @('fr_FR-siwis-medium.onnx.json', 'MODEL_CARD')) {
    $target = Join-Path $weightsRoot $name
    if (-not (Test-Path -LiteralPath $target)) {
        & curl.exe --fail --location --silent --show-error --max-time 60 --output $target "https://huggingface.co/rhasspy/piper-voices/resolve/c10ece1aade47bb51c153c893d14e5bf8e5b7117/fr/fr_FR/siwis/medium/$name"
        if ($LASTEXITCODE -ne 0) { throw 'Métadonnées de voix indisponibles' }
    }
}

$voicePython = Join-Path $runtimeRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $voicePython)) {
    & (Join-Path $voiceRoot 'backend\.venv\Scripts\python.exe') -B -m venv (Join-Path $runtimeRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Création de l’environnement vocal impossible' }
}
& $voicePython -B -m pip install --disable-pip-version-check --only-binary=:all: -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Installation vocale incomplète' }
& $voicePython -B (Join-Path $PSScriptRoot 'install_pocket_tts.py')
if ($LASTEXITCODE -ne 0) {
    throw 'Installation Pocket TTS incomplète. Vérifiez l’acceptation de la licence Kyutai et la connexion Hugging Face, puis relancez cette commande explicite.'
}
Write-Output 'Installation terminée ; les essais réels restent nécessaires.'
