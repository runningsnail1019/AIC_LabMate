$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = "$root\.venv\Scripts\python.exe"
$venvPip = "$root\.venv\Scripts\pip.exe"
$useVenv = Test-Path $venvPip
if (-not $useVenv) {
  # Some managed Windows installations disable ensurepip. In that case use
  # the installed Python 3.12 interpreter directly instead of failing early.
  py -3.12 -m pip install -r "$root\backend\requirements.txt"
  $pythonArgs = @("-3.12")
} else {
  & $venvPython -m pip install -r "$root\backend\requirements.txt"
  $pythonArgs = @($venvPython)
}
Write-Host "打开浏览器访问 http://127.0.0.1:8000"
if ($useVenv) {
  & $venvPython -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
} else {
  py -3.12 -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
}
