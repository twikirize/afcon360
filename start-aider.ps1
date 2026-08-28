# AFCON360 Aider + NVIDIA NIM launcher

$line = Get-Content .env | Select-String '^NVIDIA_API_KEY=' | Select-Object -First 1

if (-not $line) {
    Write-Host "ERROR: NVIDIA_API_KEY was not found in .env" -ForegroundColor Red
    exit 1
}

$env:NVIDIA_NIM_API_KEY = $line.ToString().Split('=',2)[1].Trim()
$env:NVIDIA_NIM_API_BASE = "https://integrate.api.nvidia.com/v1"

aider --model nvidia_nim/openai/gpt-oss-120b --no-show-model-warnings