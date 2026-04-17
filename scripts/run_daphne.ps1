$ErrorActionPreference = "Stop"
Set-Location -LiteralPath "$PSScriptRoot\.."

if (-not $env:REDIS_URL) {
  $env:REDIS_URL = "redis://127.0.0.1:6379/0"
}

if (-not $env:DJANGO_SETTINGS_MODULE) {
  $env:DJANGO_SETTINGS_MODULE = "MyFaceclone.settings"
}

& "C:/Program Files/Python313/python.exe" -m daphne -b 0.0.0.0 -p 8000 MyFaceclone.asgi:application
