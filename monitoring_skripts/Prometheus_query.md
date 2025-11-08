# Transactions per block
- sum by (instance)(
        increase(
            eth_exe_block_head_transactions_in_block[30m]
        )
    )

# Tx success rate (%)
FALLS du keine Promethius finden einfach von spammer totals: succeded / confirmed + succeded.
- GETH: 
100 *
sum by (instance) (rate(rpc_duration_eth_sendRawTransaction_success_count[5m]))
/
(
  sum by (instance) (rate(rpc_duration_eth_sendRawTransaction_success_count[5m]))
+ sum by (instance) (rate(rpc_duration_eth_sendRawTransaction_failure_count[5m]))
)
- BESU
100 * (besu_executors_ethscheduler_transactions_completed_tasks_total / (besu_executors_ethscheduler_transactions_dropped_tasks_total + besu_executors_ethscheduler_transactions_completed_tasks_total))

# AVG Transaction time 
- MIT API von DORA: eth_transaction_count #TX Count per Slot=12s 
- avg_tx_time = 12 * 1000 / eth_transaction_count #example: 12000ms / 2000x tx = 1tx dauert avg 6ms

# Throughput (TPS) Tx Per Sec
- MIT API von DORA: eth_transaction_count #TX Count per Slot=12s 
- tps = eth_transaction_count / 12s 

# Gas Used
eth_exe_block_head_gas_used

# Effective gas price (wei) or avg Gas price in wei
avg(eth_exe_gas_price_gwei{})

# Tx fee (ETH)

# Mempool size (pending)
totals: pending

# Transactions per block
- sum by (instance)(
    increase(
        eth_exe_block_head_transactions_in_block[30m]
    )
)

avg(eth_exe_block_head_transactions_in_block)

# Network utilization (%)
API "network_utilization_percentage": 40.2142

# Block utilization (%)
- per slot: DORA API: GasUsed / Gaslimit
-   sum by (instance)(
        eth_exe_block_head_gas_used
    )
    /
    sum by (instance)( 
        eth_exe_block_head_gas_limit
    )

# Block size (bytes)
- eth_exe_block_head_block_size_bytes{}
- MIT API von DORA: eth_transaction_count #TX Count per Slot=12s
    - block_size


# CPU usage (%) per node
- CPU usage (%) of the node process (share of total host CPU capacity)
- 100 * sum by (instance) (rate(process_cpu_seconds_total[30m])) / sum by (instance) (cpu_threads)
# avg cpu % per node
avg(100 * sum by (instance) (rate(process_cpu_seconds_total[30m])) / sum by (instance) (cpu_threads))
# Memory used overtime after n blocks.


# Blobs per block
- blob_count

# Blob base fee (wei per blob gas)

# Blob data throughput (MB/s)

# Disk I/O throughput (B/s) per node
# Network throughput (B/s) Network throughput (total, Mbit/s) in and out
(
  sum by (instance) (rate(network_node_bytes_total_received[5m])) +
  sum by (instance) (rate(network_node_bytes_total_transmit[5m]))
) * 8 / 1e6
## Inbound / outbound separately (Mbit/s):
sum by (instance) (rate(network_node_bytes_total_received[5m])) * 8 / 1e6
sum by (instance) (rate(network_node_bytes_total_transmit[5m])) * 8 / 1e6

# # Network throughput (B/s) per note
# Total CPU usage to run eth network
100*(1 - sum(increase(cpu_idle_seconds_total[30m])) / sum(increase(cpu_idle_seconds_total[30m]) + increase(cpu_user_seconds_total[30m]) + increase(cpu_system_seconds_total[30m]) + increase(cpu_iowait_seconds_total[30m])))

