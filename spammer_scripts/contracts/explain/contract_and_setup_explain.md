# CHATGPT CHAT!
https://chatgpt.com/share/6916fc30-a708-8009-97dd-b83278fba24a

# Installed Solc to build contracts with:
solc HighGasContract.sol \
  --bin --abi \
  -o ./build \
  --overwrite

This should produce (paths we’ll use below):
    ./build/HighGasContract.bin
    ./build/HighGasContract.abi


# Contract Overview
* **HighGasContract** → *storage-heavy, very high gas per tx*
* **HighComputeContract** → *CPU/memory-heavy, high gas per tx, low state growth*
* **LowGasSpamContract** → *very low gas per tx, designed for massive tx counts*

That’s exactly what you want for a paper: three **distinct workloads**, not three variations of the same thing.

---

## 1. Similarities (the “cross section”)

All three contracts:

* Are **state-changing**, non-view functions you call via normal transactions.
* Emit **events/logs**, so every tx leaves a trace in the log bloom.
* Are intentionally **non-functional** from a business perspective – their sole purpose is to generate load.
* Can be driven by the same Spamoor scenario type (e.g. `calltx`) just by changing:

  * the target contract address
  * the function selector / arguments.

So the intersection is mainly:

> “Contracts with simple external entrypoints that let a spammer generate **synthetic load** on the chain.”

From a research point of view, you can treat them as **three different micro-benchmarks** in the same test suite.

---

## 2. Differences – per contract

### HighGasContract

**Goal:** *Maximize gas per transaction via storage + hashing + events.*

* Tight loop with:

  * `SLOAD` and especially `SSTORE` on a mapping.
  * `KECCAK256` over changing data.
  * `emit DidWork(...)` every iteration.
* **Effects:**

  * Very **high gas per tx**.
  * **Strong state growth** (lots of new/updated storage slots).
  * Stresses:

    * EVM execution
    * State trie updates
    * Disk I/O and pruning on the node.

This is your **“storage-heavy, worst-case tx”** benchmark.

---

### HighComputeContract

**Goal:** *Burn gas on CPU + memory, not on storage.*

* Allocates a **large in-memory array** → memory expansion cost.
* Nested loops with **repeated KECCAK256 hashing**.
* Only a **single storage write** at the end (`sink`).
* **Effects:**

  * **High gas per tx**, but for a different reason than HighGasContract.
  * **Minimal state growth** (1 storage slot updated).
  * Stresses:

    * EVM **compute** (hashing, loops)
    * EVM **memory management** (expansion / copying)
    * Much less impact on the state trie/disk.

This is your **“compute/memory-heavy, state-light tx”** benchmark.

---

### LowGasSpamContract

**Goal:** *Make each tx as cheap as possible, so you can spam **many** tx.*

* `spam(uint64)` does nothing but `emit Spam(msg.sender, tag)`.
* No loops (unless you use `multiSpam`), no storage writes, no hashing.
* **Effects:**

  * **Very low gas per tx** (base cost + a tiny LOG).
  * **No state growth** (no `SSTORE` at all).
  * Stresses:

    * **Transaction throughput** (TPS)
    * Mempool, networking, and consensus, not EVM complexity.

This is your **“cheap tx flood”** benchmark.

---

## 3. How similar / different in terms of goals?

You can summarise their relationship in your paper like this:

* All three contracts are **synthetic workloads for benchmarking** a local Ethereum-style network.

* They form **three almost orthogonal profiles**:

  1. **Storage-heavy high-gas workload (HighGasContract)**

     * Few txs can already fill a block.
     * Good for studying **state growth, block execution time, disk usage**.

  2. **Compute/memory-heavy high-gas workload (HighComputeContract)**

     * Also expensive per tx, but with almost no additional state.
     * Good for studying **pure EVM execution performance** without large state bloat.

  3. **Low-gas high-volume workload (LowGasSpamContract)**

     * Individual txs are cheap; the stress comes from **sheer tx count**.
     * Good for studying **throughput, mempool behaviour, gossip, and consensus** under high load.

* The **cross section** is therefore *conceptual* (all are spam/test contracts) rather than *technical* (they don’t share the same gas profile or bottlenecks).

---

## 4. One-paragraph wording you can reuse in your paper

You could phrase it like this:

> “We design three synthetic smart contracts to generate distinct stress profiles on our test network. *HighGasContract* represents a storage-heavy workload, with each transaction performing multiple `SSTORE` and `SLOAD` operations, cryptographic hashing and event emission, resulting in very high gas consumption and rapid state growth. *HighComputeContract* instead focuses on compute and memory pressure: it allocates large memory arrays and performs nested hashing loops while touching storage only once, producing high execution cost with minimal state expansion. Finally, *LowGasSpamContract* implements a low-gas workload that emits only a small event per call, enabling us to generate a large number of inexpensive transactions. While all three contracts serve the common purpose of controlled load generation, their gas and state characteristics are intentionally disjoint, allowing us to separately evaluate storage-heavy, compute-heavy, and high-volume transaction scenarios.”

If you want, I can help you turn this into a tiny “Methodology – Workload Design” subsection with a table you can drop straight into your thesis.

