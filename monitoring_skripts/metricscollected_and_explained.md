## Transactions & fees

* **Tx success rate (%)**
  **What:** Reliability of submitted transactions.
  **How:** `successes / submitted * 100`, where success = `receipt.status == 1`.
  **From:** receipts + your submit counter.

* **Transaction time / Confirmation time (s)**
  **What:** User-visible latency from submission to inclusion.
  **How (per tx):** `receipt.block_timestamp − submit_ts` → summarize p50/p95/p99 per window.
  **From:** receipts + your `submit_ts`.

* **Gas used (per tx)**
  **What:** Execution work consumed by a tx.
  **How:** `receipt.gasUsed`.
  **From:** receipts.

* **Effective gas price (wei)**
  **What:** Actual price paid per gas unit.
  **How:** `receipt.effectiveGasPrice`.
  **From:** receipts.

* **Realized tip (wei)**
  **What:** Portion above base fee that goes to proposer.
  **How:** `receipt.effectiveGasPrice − block.baseFeePerGas`.
  **From:** receipts + block header.

* **Tx fee (ETH)**
  **What:** End-user cost per tx.
  **How:** `receipt.gasUsed * receipt.effectiveGasPrice / 1e18`.
  **From:** receipts.

---

## Mempool & throughput

* **Mempool size (pending)**
  **What:** Backlog pressure.
  **How:** `txpool_status.pending` (or “seen but not yet confirmed” set size).
  **From:** RPC `txpool_status` or WS tracking.

* **Admission rate (tx/s)**
  **What:** Ingress load into mempool.
  **How:** Count `newPendingTransactions` per second.
  **From:** WS/RPC.

* **Throughput (TPS)**
  **What:** Chain processing rate.
  **How:** `included_tx_count / window_seconds`.
  **From:** block tx counts per window.

* **Transactions per block**
  **What:** Packing density per block.
  **How:** `len(block.transactions)`.
  **From:** block body.

---

## Gas & blocks

* **Base fee (wei)**
  **What:** EIP-1559 base price signal.
  **How:** `block.baseFeePerGas`.
  **From:** block header.

* **Block gas used (value)** *(a.k.a. “Gas used Value”)*
  **What:** Absolute gas consumed by the block.
  **How:** `block.gasUsed`.
  **From:** block header.

* **Block utilization (%)** *(a.k.a. “Gas used %”)*
  **What:** How full blocks are relative to capacity.
  **How:** `block.gasUsed / block.gasLimit * 100`.
  **From:** block header.

* **Block size (bytes)**
  **What:** On-wire payload size (complements gas).
  **How:** `block.size` (if exposed by client; else infer from raw body).
  **From:** block/RPC.

---

## Reliability & API

* **RPC error rate (%)**
  **What:** Reliability of your API surface.
  **How:** `failed_rpc / total_rpc * 100`.
  **From:** proxy/harness counters.

---

## Host / node resources (per machine)

* **CPU usage (%)**
  **What:** Processor load.
  **How:** `100 * (1 − avg(rate(node_cpu_seconds_total{mode="idle"}[1m])))`.
  **From:** Prometheus node-exporter.

* **Memory used (%)**
  **What:** RAM pressure.
  **How:** `100 * (1 − node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)`.
  **From:** node-exporter.

* **Disk I/O throughput (B/s)**
  **What:** Storage pressure during runs.
  **How:**
  • Read: `sum(rate(node_disk_read_bytes_total[1m]))`
  • Write: `sum(rate(node_disk_written_bytes_total[1m]))`
  *(Filter out loop/ram devices as needed.)*
  **From:** node-exporter.

* **Network throughput (B/s)**
  **What:** P2P/RPC bandwidth load.
  **How:**
  • RX: `sum(rate(node_network_receive_bytes_total{device!="lo"}[1m]))`
  • TX: `sum(rate(node_network_transmit_bytes_total{device!="lo"}[1m]))`
  **From:** node-exporter.

---

## System-wide aggregates (entire local network)

* **Total system CPU use (%)**
  **What:** Aggregate compute burn across all nodes.
  **How:**
  `100 * sum(rate(node_cpu_seconds_total{mode!="idle"}[1m])) / sum(rate(node_cpu_seconds_total[1m]))`
  *(Add `by(phase)` to split baseline vs attack.)*
  **From:** node-exporter (all hosts).

* **Total system memory used (bytes, %)**
  **What:** Aggregate RAM consumed by the network.
  **How (bytes):** `sum(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes)`
  **How (%):** `100 * sum(MemTotal - MemAvailable) / sum(MemTotal)`
  **From:** node-exporter (all hosts).

---

## Blob (EIP-4844) metrics (pick 1–3)

* **Blobs per block**
  **What:** Data-availability (DA) usage intensity.
  **How:** Count blobs across 4844 txs per block (sum lengths of `blob_versioned_hashes`).
  **From:** execution payload / RPC.

* **Blob base fee (wei per blob gas)**
  **What:** DA price signal (4844 analogue of base fee).
  **How:** Read from payload (commonly `blobBaseFee`) or derive from `excessBlobGas`. Track avg/p95.
  **From:** execution payload / RPC.

* **Blob data throughput (MB/s)**
  **What:** Real DA bandwidth over time.
  **How:** `(num_blobs * 131072) / window_seconds / 1e6` (1 blob ≈ 131,072 bytes).
  **From:** blob counts per window.

---

### Implementation tips

* **Tag every row:** `phase` (`baseline`/`attack`), ISO8601 `timestamp`, `node_id/client`.
* **Percentiles:** compute over fixed windows (e.g., 1–5 min) for stability.
* **Units:** keep `wei` vs `ETH` explicit; store raw then format for plots.

If you want, I can turn this into a one-page appendix table you can paste directly into your thesis.
