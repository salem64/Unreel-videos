# Unreel v2 upgrade: Z-Image Turbo (start frames), Wan 2.2 14B I2V fp8 + lightx2v 4-step LoRAs, RIFE interpolation.
# Needs the v1 install (install.ps1) first. Adds ~55 GB of models.
# Run:  $env:UNREEL_ROOT="D:\Unreel"; irm https://raw.githubusercontent.com/salem64/Unreel-videos/main/pc/install_v2.ps1 | iex
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Step($t) { Write-Host ""; Write-Host "=== $t ===" -ForegroundColor Cyan }
function Get-File($url, $out) {
    if (Test-Path "$out.done") { Write-Host "  vorhanden: $(Split-Path $out -Leaf)"; return }
    New-Item -ItemType Directory -Force -Path (Split-Path $out) | Out-Null
    Write-Host "  lade: $(Split-Path $out -Leaf)"
    & curl.exe -L --fail --retry 5 --retry-delay 5 -C - -o $out $url
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 33) { throw "Download fehlgeschlagen: $url (curl $LASTEXITCODE)" }
    New-Item -ItemType File -Force -Path "$out.done" | Out-Null
}

$root = $env:UNREEL_ROOT
if (-not $root) { $root = (Get-Content "D:\Unreel\unreel_root.txt" -ErrorAction SilentlyContinue) }
if (-not $root) { throw "Bitte zuerst `$env:UNREEL_ROOT setzen (z. B. D:\Unreel)" }
$cuRoot = Join-Path $root "ComfyUI_windows_portable"
$py = Join-Path $cuRoot "python_embeded\python.exe"
$cu = Join-Path $cuRoot "ComfyUI"
if (-not (Test-Path $py)) { throw "ComfyUI nicht gefunden unter $cuRoot - zuerst install.ps1 ausfuehren" }

Step "Systemcheck"
$freeGB = [math]::Round((Get-PSDrive ((Get-Item $root).PSDrive.Name)).Free / 1GB)
$ramGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
Write-Host "Freier Speicher: $freeGB GB, Arbeitsspeicher: $ramGB GB"
if ($freeGB -lt 60) { throw "Zu wenig Speicher: v2 braucht ca. 60 GB frei auf $root" }
if ($ramGB -lt 32) { Write-Warning "Weniger als 32 GB RAM - das 14B-Modell kann sehr langsam werden (Auslagerungsdatei)." }

Step "Frame-Interpolation (RIFE)"
$fi = Join-Path $cu "custom_nodes\ComfyUI-Frame-Interpolation"
if (-not (Test-Path $fi)) { git clone --depth 1 https://github.com/Fannovel16/ComfyUI-Frame-Interpolation $fi }
Push-Location $fi
& $py -s install.py
Pop-Location

Step "Modelle v2 (ca. 55 GB)"
$hf = "https://huggingface.co"
$w22 = "$hf/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files"
Get-File "$w22/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors" (Join-Path $cu "models\diffusion_models\wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors")
Get-File "$w22/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors" (Join-Path $cu "models\diffusion_models\wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors")
Get-File "$w22/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors" (Join-Path $cu "models\loras\wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors")
Get-File "$w22/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors" (Join-Path $cu "models\loras\wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors")
Get-File "$w22/vae/wan_2.1_vae.safetensors" (Join-Path $cu "models\vae\wan_2.1_vae.safetensors")
$zi = "$hf/Comfy-Org/z_image_turbo/resolve/main/split_files"
Get-File "$zi/diffusion_models/z_image_turbo_bf16.safetensors" (Join-Path $cu "models\diffusion_models\z_image_turbo_bf16.safetensors")
Get-File "$zi/text_encoders/qwen_3_4b.safetensors" (Join-Path $cu "models\text_encoders\qwen_3_4b.safetensors")
Get-File "$zi/vae/ae.safetensors" (Join-Path $cu "models\vae\ae.safetensors")

Step "Repo aktualisieren"
git -C (Join-Path $root "Unreel-videos") pull

Step "Fertig"
Write-Host "v2 installiert. Auftraege mit 'image_prompt' nutzen ab jetzt automatisch die v2-Pipeline." -ForegroundColor Green
