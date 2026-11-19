# Reference files from the paper-2 repository

Copied unchanged from https://github.com/imanejerrari-etu-bit/cross-db-replication-mode-selection
(commit 6022629, MIT license for code). They are NOT used by the pilot; they are here
to reuse in the full study:

- common.py: seed (42), feature list, class names, RandomForest parameters.
- generate_datasets.py: the rule-based generator whose labels the new study replaces by MEASURED labels.
- failover_test_postgres.py: failover harness (pod deletion, promotion/stabilisation timing) to reuse for the AVAILABILITY / fault-injection windows.
- postgres-cluster.yaml: paper-2 cluster definition (the pilot uses k8s/cluster.yaml with fixed 1 CPU / 1 GiB).
- requirements-lock.txt: pinned versions that reproduced paper 2.
