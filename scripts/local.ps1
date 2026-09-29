param([ValidateSet('start', 'stop', 'status', 'key')][string]$Action = 'start')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$toolsRoot = Join-Path (Split-Path $projectRoot -Parent) '.tools'
$python = Join-Path $toolsRoot 'python\python.exe'
$runtime = Join-Path $projectRoot '.local'
$stateFile = Join-Path $runtime 'processes.json'
Set-Location -LiteralPath $projectRoot

function Load-LocalEnvironment {
    Get-Content -LiteralPath (Join-Path $projectRoot '.env.local') | ForEach-Object {
        if ($_ -match '^([A-Z_]+)=(.*)$') {
            [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process')
        }
    }
}
function Is-Running($record) {
    $process = Get-Process -Id $record.id -ErrorAction SilentlyContinue
    return ($process -and $process.StartTime.ToUniversalTime().Ticks.ToString() -eq $record.started)
}
function Wait-Port([int]$port) {
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        $client = New-Object System.Net.Sockets.TcpClient
        try { $client.Connect('127.0.0.1', $port); return } catch { Start-Sleep -Milliseconds 500 }
        finally { $client.Dispose() }
    }
    throw "Service on port $port did not start. Inspect .local logs."
}
$records = @()
if (Test-Path -LiteralPath $stateFile) { $records = Get-Content $stateFile -Raw | ConvertFrom-Json }
if ($Action -eq 'key') {
    Load-LocalEnvironment
    Set-Clipboard -Value $env:ADMIN_API_KEY
    Write-Output 'Operator key copied. Paste it into the workspace connection form.'
    exit
}
if ($Action -eq 'status') {
    Load-LocalEnvironment
    & $python scripts/check_deployment.py --env-file .env.local
    exit $LASTEXITCODE
}
if ($Action -eq 'stop') {
    foreach ($name in @('api', 'worker', 'redis', 'postgres')) {
        $record = $records | Where-Object name -eq $name | Select-Object -Last 1
        if ($record -and (Is-Running $record)) {
            if ($name -eq 'postgres') {
                & (Join-Path $toolsRoot 'postgres\pgsql\bin\pg_ctl.exe') stop -D (Join-Path $toolsRoot 'local-pgdata') -m fast -w
                if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL did not shut down cleanly.' }
            } elseif ($name -eq 'redis') {
                Load-LocalEnvironment
                & $python scripts/local_setup.py stop-redis
                if ($LASTEXITCODE -ne 0) { throw 'Redis did not shut down cleanly.' }
            } else { Stop-Process -Id $record.id }
        }
    }
    Write-Output 'Local services stopped. Database and Redis data are preserved.'
    exit
}
if (-not (Test-Path (Join-Path $projectRoot 'frontend\dist\index.html'))) {
    throw 'Build the frontend first: cd frontend; npm.cmd run build'
}
& $python scripts/local_setup.py prepare
if ($LASTEXITCODE -ne 0) { throw 'Local setup failed.' }
Load-LocalEnvironment
function Start-ServiceProcess($name, $executable, $arguments, $workingDirectory) {
    $existing = $script:records | Where-Object name -eq $name | Select-Object -Last 1
    if ($existing -and (Is-Running $existing)) { return }
    $process = Start-Process -FilePath $executable -ArgumentList $arguments -WorkingDirectory $workingDirectory -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime "$name.out.log") -RedirectStandardError (Join-Path $runtime "$name.err.log")
    $script:records = @($script:records | Where-Object name -ne $name) + @(@{name=$name; id=$process.Id; started=$process.StartTime.ToUniversalTime().Ticks.ToString()})
    ConvertTo-Json -InputObject $script:records -Depth 4 | Set-Content -LiteralPath $stateFile
    Start-Sleep -Milliseconds 750
    $process.Refresh()
    if ($process.HasExited) { throw "$name exited during startup. Inspect .local logs." }
}
Start-ServiceProcess 'postgres' (Join-Path $toolsRoot 'postgres\pgsql\bin\postgres.exe') @('-D', ('"' + (Join-Path $toolsRoot 'local-pgdata') + '"'), '-h', '127.0.0.1', '-p', '55433') $projectRoot
Wait-Port 55433
& $python scripts/local_setup.py database
if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
$redis = Join-Path $toolsRoot 'redis\Redis-7.4.11-Windows-x64-msys2\redis-server.exe'
Start-ServiceProcess 'redis' $redis @('redis.conf') $runtime
Wait-Port 56379
Start-ServiceProcess 'worker' $python @('-m', 'market_data.worker') $projectRoot
Start-ServiceProcess 'api' $python @('-m', 'uvicorn', 'api.local:app', '--host', '127.0.0.1', '--port', '8080', '--no-access-log') $projectRoot
Wait-Port 8080
Start-Sleep -Seconds 2
& $python scripts/check_deployment.py --base-url http://127.0.0.1:8080 --env-file .env.local
if ($LASTEXITCODE -ne 0) { throw 'Local smoke check failed. Inspect .local logs.' }
Set-Clipboard -Value $env:ADMIN_API_KEY
Write-Output 'App ready at http://localhost:8080. Operator key copied to clipboard; paste it into the connection form.'
