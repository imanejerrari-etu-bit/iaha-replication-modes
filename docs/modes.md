# Mapping of the four replication modes to CloudNativePG

The semantics of the modes come from the first paper of the series (asynchronous with one replica;
synchronous with two replicas; synchronous with standby reads; scaled-down asynchronous). The mapping
below to operator parameters and instance counts is an operationalisation by the authors
(`MODES` in `pilot/grid_run.py`).

| Mode | instances | minSyncReplicas / maxSyncReplicas | Reads served by | Durable | HA | Cost |
|---|---|---|---|---|---|---|
| PERFORMANCE | 2 | 0 / 0 | primary | no | yes | 2 |
| CONSISTENCY | 3 | 2 / 2 | primary | yes | yes | 3 |
| AVAILABILITY | 3 | 1 / 1 | standbys | yes | yes | 3 |
| ECONOMIC | 1 | 0 / 0 | primary | no | no | 1 |

"Cost" is the number of instances. Changing the mapping changes the results.
