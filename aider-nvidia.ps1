$line = Get-Content .env | Where-Object { $_ -match '^NVIDIA_API_KEY\s*=' } | Select-Object -First 1
$env:OPENAI_API_KEY = ($line -split '=', 2)[1].Trim().Trim('"').Trim("'")

aider --model openai/gpt-oss-120b --openai-api-base https://integrate.api.nvidia.com/v1 --subtree-only
