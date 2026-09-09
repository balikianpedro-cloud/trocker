# setup_hp.ps1 — instala o Trocker no HP (Windows 11, sem GPU NVIDIA, Python 3.12)
# Uso: pwsh -ExecutionPolicy Bypass -File .\setup_hp.ps1
$ErrorActionPreference = "Stop"
$Py   = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
$Venv = "$env:USERPROFILE\venvs\trockerv"        # fora do OneDrive (evita sync de milhares de arquivos)
$Repo = $PSScriptRoot

if (-not (Test-Path $Py)) { throw "Python 3.12 nao encontrado em $Py. Instale: winget install Python.Python.3.12" }

if (-not (Test-Path "$Venv\Scripts\python.exe")) {
    New-Item -ItemType Directory -Force (Split-Path $Venv) | Out-Null
    & $Py -m venv $Venv
}
$VPy = "$Venv\Scripts\python.exe"
& $VPy -m pip install --upgrade pip wheel
# PyTorch CPU (o HP tem apenas Intel UHD 630)
& $VPy -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
& $VPy -m pip install -r "$Repo\requirements.txt" requests openpyxl

# FFmpeg no PATH (usado para cortar/recodificar videos)
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements --silent
}

# Verificacao
& $VPy -c "import torch, ultralytics, PySide6, cv2; from boxmot import ByteTrack, BotSort, StrongSort; print('OK torch', torch.__version__, '| cuda', torch.cuda.is_available(), '| ultralytics', ultralytics.__version__, '| PySide6', PySide6.__version__)"
Write-Host "`nPronto. Para abrir o app: $Repo\trocker_hp.bat" -ForegroundColor Green
