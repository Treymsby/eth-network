I am targeting a network utulization of around 50% Since EIP-1559, the target gas per block = 50% of the gas_limit, and utilization oscillates around that.

#Setups
GETH - Lighthouse
GETH - Prysm
BESU - Lighthouse
BESU - Prysm
GETH - Lighthouse (Max peer = 16 Connection, CL Target Peer = 16 Fully Meshed)
Mixed

Why Nethermind (C#/.NET)

Why vs Geth: very different implementation stack + competitive performance; good EIP-4844/blob support; rich tracing/JSON-RPC; strong metrics out of the box.

Good for: performance + mempool/blob behavior comparisons under realistic load; profiling and instrumentation.
