# Network Usage
## Inbound / outbound separately (Mbit/s):
sum by (instance) (rate(network_node_bytes_total_received[5m])) * 8 / 1e6
sum by (instance) (rate(network_node_bytes_total_transmit[5m])) * 8 / 1e6
## Receive Delay (Network deplay)
API DORA recv_delay

# Memory Usage
## Memory usage over time per node:
process_resident_memory_bytes
## Memory usage per code via time in Cores
http://127.0.0.1:33263/d/2BrpaEr7k/ethereum-metrics-exporter-overview?orgId=1&from=now-30m&to=now&timezone=browser&var-filter=&refresh=1m&viewPanel=panel-58



# CPU Usage
## CPU Usage per code via time in Cores
http://127.0.0.1:33263/d/2BrpaEr7k/ethereum-metrics-exporter-overview?orgId=1&from=now-30m&to=now&timezone=browser&var-filter=&refresh=1m&viewPanel=panel-57

## CPU
irate(process_cpu_seconds_total[1m]) #all nodes
irate(process_cpu_seconds_total{instance=~"$system", job=~".*besu.*|execution.*"}[1m])
irate(process_cpu_seconds_total{instance=~"$system", job=~".*geth.*|execution.*"}[1m])
irate(process_cpu_seconds_total{instance=~"$system", job=~".*nethermind.*|execution.*"}[1m])

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
## Total gas used
API Blocksout Total Gas used: SUM("gas_used" per block)
## Gas used per block 
API Blocksout
## Gas Used per block per node
eth_exe_block_head_gas_used
## Effective gas price (wei) or avg Gas price in wei (over time)
http://127.0.0.1:33263/d/2BrpaEr7k/ethereum-metrics-exporter-overview?orgId=1&from=now-30m&to=now&timezone=browser&var-filter=&refresh=1m&viewPanel=panel-38

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

# Mempool size
totals: pending (spaamoor api) per block