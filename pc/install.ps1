# Unreel PC setup (Windows + NVIDIA). Installs ComfyUI portable, Wan 2.2 5B, MMAudio and the render worker.
# Run in PowerShell:  irm https://raw.githubusercontent.com/salem64/Unreel-videos/main/pc/install.ps1 | iex
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Step($t) { Write-Host ""; Write-Host "=== $t ===" -ForegroundColor Cyan }
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}
function Get-File($url, $out) {
    if (Test-Path "$out.done") { Write-Host "  vorhanden: $(Split-Path $out -Leaf)"; return }
    New-Item -ItemType Directory -Force -Path (Split-Path $out) | Out-Null
    Write-Host "  lade: $(Split-Path $out -Leaf)"
    & curl.exe -L --fail --retry 5 --retry-delay 5 -C - -o $out $url
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 33) { throw "Download fehlgeschlagen: $url (curl $LASTEXITCODE)" }
    New-Item -ItemType File -Force -Path "$out.done" | Out-Null
}

Step "Unreel PC Setup"
$default = "C:\Unreel"
if ($env:UNREEL_ROOT) { $root = $env:UNREEL_ROOT } else { $root = Read-Host "Installationsordner (Enter = $default, braucht ca. 45 GB)" }
if ([string]::IsNullOrWhiteSpace($root)) { $root = $default }
New-Item -ItemType Directory -Force -Path $root | Out-Null
$freeGB = [math]::Round((Get-PSDrive ((Get-Item $root).PSDrive.Name)).Free / 1GB)
Write-Host "Freier Speicher auf dem Laufwerk: $freeGB GB"
if ($freeGB -lt 45) { Write-Warning "Weniger als 45 GB frei - Setup kann fehlschlagen." }

Step "Grafikkarte"
try { & nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader } catch { Write-Warning "nvidia-smi nicht gefunden - ist der NVIDIA-Treiber installiert?" }

Step "Git und 7-Zip"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements
    Refresh-Path
}
$7z = "C:\Program Files\7-Zip\7z.exe"
if (-not (Test-Path $7z)) {
    winget install --id 7zip.7zip -e --accept-source-agreements --accept-package-agreements
}
if (-not (Test-Path $7z)) { throw "7-Zip nicht gefunden unter $7z" }
git --version

Step "ComfyUI (portable, NVIDIA)"
$cuRoot = Join-Path $root "ComfyUI_windows_portable"
if (-not (Test-Path (Join-Path $cuRoot "python_embeded\python.exe"))) {
    $archive = Join-Path $root "ComfyUI_windows_portable_nvidia.7z"
    Get-File "https://github.com/Comfy-Org/ComfyUI/releases/latest/download/ComfyUI_windows_portable_nvidia.7z" $archive
    & $7z x $archive "-o$root" -y | Out-Null
    if (-not (Test-Path (Join-Path $cuRoot "python_embeded\python.exe"))) { throw "ComfyUI konnte nicht entpackt werden" }
    Remove-Item $archive, "$archive.done" -Force -ErrorAction SilentlyContinue
}
$py = Join-Path $cuRoot "python_embeded\python.exe"
$cu = Join-Path $cuRoot "ComfyUI"

Step "MMAudio-Erweiterung (Sound zum Video)"
$mmNode = Join-Path $cu "custom_nodes\ComfyUI-MMAudio"
if (-not (Test-Path $mmNode)) { git clone --depth 1 https://github.com/kijai/ComfyUI-MMAudio $mmNode }
& $py -s -m pip install -r (Join-Path $mmNode "requirements.txt")
& $py -s -m pip install imageio-ffmpeg huggingface_hub

Step "Modelle (ca. 22 GB, dauert je nach Internet 15-60 Min)"
$hf = "https://huggingface.co"
Get-File "$hf/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors" (Join-Path $cu "models\diffusion_models\wan2.2_ti2v_5B_fp16.safetensors")
Get-File "$hf/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan2.2_vae.safetensors" (Join-Path $cu "models\vae\wan2.2_vae.safetensors")
Get-File "$hf/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" (Join-Path $cu "models\text_encoders\umt5_xxl_fp8_e4m3fn_scaled.safetensors")
foreach ($f in @("mmaudio_large_44k_v2_fp16.safetensors", "mmaudio_vae_44k_fp16.safetensors", "mmaudio_synchformer_fp16.safetensors", "apple_DFN5B-CLIP-ViT-H-14-384_fp16.safetensors")) {
    Get-File "$hf/Kijai/MMAudio_safetensors/resolve/main/$f" (Join-Path $cu "models\mmaudio\$f")
}

Step "Unreel-Repo"
$repo = Join-Path $root "Unreel-videos"
if (-not (Test-Path (Join-Path $repo ".git"))) { git clone https://github.com/salem64/Unreel-videos $repo }
git -C $repo pull
git -C $repo config user.name "unreel-pc"
git -C $repo config user.email "unreel@users.noreply.github.com"
Write-Host "GitHub-Anmeldung pruefen (es kann sich ein Browserfenster oeffnen - bitte mit salem64 anmelden)..."
git -C $repo push --dry-run

Step "Startdatei auf dem Desktop"
$bat = Join-Path ([Environment]::GetFolderPath("Desktop")) "Unreel Batch starten.bat"
@"
@echo off
title Unreel Batch
"$py" -s "$repo\pc\worker.py" --root "$root"
echo.
echo Fertig. Fenster kann geschlossen werden.
pause
"@ | Set-Content -Path $bat -Encoding ASCII
Set-Content -Path (Join-Path $root "unreel_root.txt") -Value $root

Step "Fertig"
Write-Host "Setup abgeschlossen. Zum Rendern: 'Unreel Batch starten' auf dem Desktop doppelklicken." -ForegroundColor Green
Write-Host "Erster Lauf: Ein Testvideo wird gerendert; MMAudio laedt dabei noch einmalig ca. 0.5 GB nach."
