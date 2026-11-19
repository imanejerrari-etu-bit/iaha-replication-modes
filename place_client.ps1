# place_client.ps1 - (re)create the pgbench client pod on the same node as the PostgreSQL primary.
#   powershell -ExecutionPolicy Bypass -File .\place_client.ps1
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
$Ctx = "kind-iaha-pilot"

$primary = kubectl --context $Ctx get cluster iaha-pg -o "jsonpath={.status.currentPrimary}"
if (-not $primary) { throw "Cannot find the primary pod." }
$node = kubectl --context $Ctx get pod $primary -o "jsonpath={.spec.nodeName}"
if (-not $node) { throw "Cannot find the primary's node." }
Write-Host "Primary $primary runs on $node -> placing pgbench-client there"

kubectl --context $Ctx delete pod pgbench-client --ignore-not-found --wait=true
(Get-Content -Raw k8s\pgbench-client.yaml).Replace("__NODE__", $node) | kubectl --context $Ctx apply -f -
if ($LASTEXITCODE -ne 0) { throw "Could not create pgbench-client." }
kubectl --context $Ctx wait --for=condition=Ready pod/pgbench-client --timeout=180s
if ($LASTEXITCODE -ne 0) { throw "pgbench-client not ready." }
Write-Host "pgbench-client is ready on $node" -ForegroundColor Green
