# Explain Prameters file
Only letting network run for 30min

## Explain min/max cpu/ram in parameter
- Link to chat: https://chatgpt.com/s/t_69109954a464819192579be8254649c2
* **`min_cpu` / `min_mem`** = the *minimum* resources the container is guaranteed. On Kubernetes these become the **request**s used by the scheduler. (Ignored on Docker.) ([docs.kurtosis.com][1])
* **`max_cpu` / `max_mem`** = the *maximum* the container may use. On Kubernetes these are the **limit**s; on Docker they’re enforced with container runtime flags (e.g. `--cpus`, `--memory`). ([docs.kurtosis.com][1])

**If `min == max`:**

* On **Kubernetes** you’re setting request = limit, so the Pod gets the **Guaranteed** QoS class; it can’t burst above that CPU, and if it tries to use more than the memory limit it’s OOMKilled. ([Kubernetes][2])
* On **Docker**, `min_*` is ignored; it behaves the same as setting only the `max_*` cap. ([docs.kurtosis.com][1])

How it works under the hood

* In Kurtosis, those YAML fields (often exposed per container type like `el_min_cpu`, `el_max_mem`, etc., in Ethereum packages) are passed into the **ServiceConfig**. Kurtosis then maps them to Kubernetes requests/limits or Docker resource flags when it starts the containers. Units are **millicpu** for CPU (1000 = 1 vCPU) and **MB** for memory. ([docs.kurtosis.com][1])

Practical effects

* **CPU**: You’re guaranteed at least `min_cpu` if the node has capacity; usage can rise up to `max_cpu` but not beyond (throttling occurs at the limit). ([Kubernetes][3])
* **Memory**: The container can’t exceed `max_mem`; crossing it leads to an OOM kill. The scheduler uses `min_mem` to place the Pod. ([Kubernetes][4])

Example (Kubernetes semantics):

```yaml
# half a core guaranteed, up to 2 cores; 1 GiB guaranteed, capped at 2 GiB
el_min_cpu: 500       # 500 millicpu = 0.5 vCPU
el_max_cpu: 2000      # 2 vCPU
el_min_mem: 1024      # MB
el_max_mem: 2048      # MB
```

Same idea exists for `cl_*` and `vc_*` container entries in common Kurtosis Ethereum packages. ([ethpandaops.io][5])

If you want, tell me which backend you’re using (Docker vs. Kubernetes) and I’ll suggest sensible starting values for each container type.

[1]: https://docs.kurtosis.com/api-reference/starlark-reference/service-config/ "ServiceConfig | Kurtosis Docs"
[2]: https://kubernetes.io/docs/tasks/configure-pod-container/quality-service-pod/?utm_source=chatgpt.com "Configure Quality of Service for Pods"
[3]: https://kubernetes.io/docs/tasks/configure-pod-container/assign-cpu-resource/?utm_source=chatgpt.com "Assign CPU Resources to Containers and Pods"
[4]: https://kubernetes.io/docs/tasks/configure-pod-container/assign-memory-resource/?utm_source=chatgpt.com "Assign Memory Resources to Containers and Pods"
[5]: https://ethpandaops.io/posts/kurtosis-deep-dive/ "Kurtosis: A Deep Dive to Local Devnets | ethPandaOps"
## 
Prometheus	200m → 500m	512Mi → 1Gi	Keep retention short (6–12h) and scrape every 30–60s to shrink memory; RAM scales with active series (~3 kB/series). 
robustperception.io
+1
Grafana	100m → 300m	256Mi → 512Mi	Disable image rendering + alerting if not needed; Grafana itself is light (official min ~512 MB, 1 core). 
Grafana Labs
+1
Dora (beacon slot explorer)	100m → 300m	256Mi → 512Mi	It’s intentionally lightweight; can even run in-memory. Use Postgres only if you want persistence. 
GitHub
Spamoor (tx spammer)	100m → 300m	128Mi → 512Mi	Scales with throughput; for burst tests raise CPU to 500m–1 core. 
GitHub
Blockscout – web/indexer	500m → 2 cores	1Gi → 3Gi	Heavy even on small chains; indexer speed will drop when constrained. 
docs.blockscout.com
Blockscout – Postgres	300m → 1 core	1Gi → 2Gi	Put limits here too; slow but OK for tiny devnets. Bigger chains need much more