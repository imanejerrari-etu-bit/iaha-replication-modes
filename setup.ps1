# setup.ps1 - one-time environment setup for the IAHA pilot.
# Run from this folder:  powershell -ExecutionPolicy Bypass -File .\setup.ps1
$ErrorActionPreference = "Continue"   # native stderr warnings must not abort; failures are checked via $LASTEXITCODE
Set-Location $PSScriptRoot

$Cluster = "iaha-pilot"
$Ctx     = "kind-$Cluster"
$CnpgUrl = "https://github.com/cloudnative-pg/cloudnative-pg/releases/download/v1.22.0/cnpg-1.22.0.yaml"

function Need($c) {
    if (-not (Get-Command $c -ErrorAction SilentlyContinue)) { throw "Missing tool: $c" }
}
function Run {
    & $args[0] $args[1..($args.Count - 1)]
    if ($LASTEXITCODE -ne 0) { throw "Command failed: $($args -join ' ')" }
}

Write-Host "== 1/7 Checking tools" -ForegroundColor Cyan
Need docker; Need kind; Need kubectl; Need python
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker Desktop is not running." }

$others = kind get clusters 2>$null | Where-Object { $_ -ne $Cluster }
if ($others) {
    Write-Host "WARNING: other kind clusters are running: $($others -join ', ')." -ForegroundColor Yellow
    Write-Host "They use RAM/CPU and add noise. Delete them if no longer needed: kind delete cluster --name <name>" -ForegroundColor Yellow
}

Write-Host "== 2/7 Python virtual environment" -ForegroundColor Cyan
if (-not (Test-Path ".venv")) { Run python -m venv .venv }
Run .\.venv\Scripts\python.exe -m pip install --quiet -r requirements-pilot.txt

Write-Host "== 3/7 kind cluster ($Cluster, 1 control-plane + 3 workers)" -ForegroundColor Cyan
$existing = kind get clusters 2>$null
if ($existing -notcontains $Cluster) {
    Run kind create cluster --name $Cluster --config k8s\kind-config.yaml
} else {
    Write-Host "Cluster already exists, reusing it."
}

Write-Host "== 4/7 CloudNativePG operator v1.22.0" -ForegroundColor Cyan
Run kubectl --context $Ctx apply --server-side -f $CnpgUrl
Run kubectl --context $Ctx -n cnpg-system rollout status deployment/cnpg-controller-manager --timeout=180s

Write-Host "== 5/7 PostgreSQL cluster + pgbench client" -ForegroundColor Cyan
Run kubectl --context $Ctx apply -f k8s\cluster.yaml
$deadline = (Get-Date).AddMinutes(12)
do {
    Start-Sleep -Seconds 5
    $phase = kubectl --context $Ctx get cluster iaha-pg -o "jsonpath={.status.phase}" 2>$null
    Write-Host "  cluster phase: $phase"
} until ($phase -eq "Cluster in healthy state" -or (Get-Date) -gt $deadline)
if ($phase -ne "Cluster in healthy state") { throw "PostgreSQL cluster not healthy after 12 min." }
& "$PSScriptRoot\place_client.ps1"

Write-Host "== 6/7 tc (netem) available in worker nodes?" -ForegroundColor Cyan
$workers = kind get nodes --name $Cluster | Where-Object { $_ -like "*worker*" }
foreach ($n in $workers) {
    docker exec $n tc -V *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  installing iproute2 in $n"
        Run docker exec $n sh -c "apt-get update -qq && apt-get install -y -qq iproute2"
    }
    Write-Host "  $n : tc OK"
}

Write-Host "== 7/7 Placement check" -ForegroundColor Cyan
kubectl --context $Ctx get pods -o wide
$nodes = (kubectl --context $Ctx get pods -l cnpg.io/cluster=iaha-pg -o "jsonpath={.items[*].spec.nodeName}") -split " " | Sort-Object -Unique
if ($nodes.Count -ne 3) { throw "The 3 PostgreSQL pods must be on 3 different nodes (found $($nodes.Count))." }

Write-Host "`nSetup complete. Next: .\run_pilot.ps1 -Quick   (smoke test), then .\run_pilot.ps1" -ForegroundColor Green
