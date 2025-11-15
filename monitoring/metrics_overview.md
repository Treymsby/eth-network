# Network Usage
## Inbound / outbound separately (Mbit/s):
(rate(network_node_bytes_total_transmit{client_type="beacon" }[5m])) * 8 / 1e6

(rate(network_node_bytes_total_received{client_type="beacon" }[5m])) * 8 / 1e6

premade:


---------------------------------


# Memory Usage
## Memory usage over time per node:
from /home/trey-mosby/Project/eth-network/monitoring/python/live_collection/cpu_mem_net_colletion.py



# CPU Usage
from /home/trey-mosby/Project/eth-network/monitoring/python/live_collection/cpu_mem_net_colletion.py


-------------------------------------
### GETH in vCPU if 1 then approx 1 CPU core (CPU cores used)
rate(system_cpu_sysload_total{client_type="execution"}[1m])

### Others in vCPU if 1 then approx 1 CPU core (CPU cores used)
rate(process_cpu_seconds_total{client_type="execution"}[1m]) * 75

premade:
/explore?schemaVersion=1&panes=%7B%22qy8%22:%7B%22datasource%22:%22PBFA97CFB590B2093%22,%22queries%22:%5B%7B%22refId%22:%22A%22,%22expr%22:%22rate%28system_cpu_sysload_total%7Bclient_type%3D%5C%22execution%5C%22%7D%5B1m%5D%29%22,%22range%22:true,%22instant%22:true,%22datasource%22:%7B%22type%22:%22prometheus%22,%22uid%22:%22PBFA97CFB590B2093%22%7D,%22editorMode%22:%22code%22,%22legendFormat%22:%22__auto%22%7D,%7B%22refId%22:%22B%22,%22expr%22:%22rate%28process_cpu_seconds_total%7Bclient_type%3D%5C%22execution%5C%22%7D%5B1m%5D%29%20%2A%2075%22,%22range%22:true,%22instant%22:true,%22datasource%22:%7B%22type%22:%22prometheus%22,%22uid%22:%22PBFA97CFB590B2093%22%7D,%22editorMode%22:%22code%22,%22legendFormat%22:%22__auto%22%7D%5D,%22range%22:%7B%22from%22:%22now-1h%22,%22to%22:%22now%22%7D,%22compact%22:false%7D%7D&orgId=1
--------------------------------------


# Block Metrics
## Network utilization (%)
API blockscout
## Block utilization (%)
API blockscout block: gas_used_percentage
## Block size (bytes)
API DORA ALL SLOTS: "block_size" in byte
API blocksout block: "size"
## Block time per block


# Gas Metrics
## Total gas used overtime
API Blocksout Total Gas used: SUM("gas_used" per block)
## Gas used per block 
API Blocksout
## Gas Used per block per node (explain, time delay, latency low da internes netzwerk)
eth_exe_block_head_gas_used
## Effective gas price (wei) or avg Gas price in wei (over time)
http://127.0.0.1:33263/d/2BrpaEr7k/ethereum-metrics-exporter-overview?orgId=1&from=now-30m&to=now&timezone=browser&var-filter=&refresh=1m&viewPanel=panel-38
make avg:

# Transaction Metrics
## AVG Transaction time
- MIT API von DORA: eth_transaction_count #TX Count per Slot=12s 
- avg_tx_time = 12 * 1000 / eth_transaction_count #example: 12000ms / 2000x tx = 1tx dauert avg 6ms

# Throughput (TPS) Tx Per Sec
- MIT API von DORA: eth_transaction_count #TX Count per Slot=12s 
- tps = eth_transaction_count / 12s 

# Tx per block
- DORA API exec_transactions_count per block

## Confimration time / Latency of Transation
tx_latency_log.jsonl via python script

## Transaction sucess rate %
all "result": "success" tx / total transations
And tx_latency.py via success / total transations (200)

# Mempool size (schau mit welsche node er verbunden ist. Nachschauen wie Pending implementiert ist.)
totals: pending (spaamoor api) per block
"totals":
    "pending": 117,

