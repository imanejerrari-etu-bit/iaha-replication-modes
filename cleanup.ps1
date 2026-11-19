# cleanup.ps1 - remove emulated network delay; optionally delete the cluster.
#   .\cleanup.ps1                 reset netem only
#   .\cleanup.ps1 -DeleteCluster  also delete the kind cluster
param([switch]$DeleteCluster)
$Cluster = "iaha-pilot"
$workers = kind get nodes --name $Cluster 2>$null | Where-Object { $_ -like "*worker*" }
foreach ($n in $workers) {
    docker exec $n tc qdisc del dev eth0 root *> $null
    Write-Host "netem reset on $n"
}
if ($DeleteCluster) { kind delete cluster --name $Cluster }
