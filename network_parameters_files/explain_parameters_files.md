🧱 EL — Execution Layer

Examples: Geth, Nethermind, Besu, Erigo
Purpose:
Runs the EVM (Ethereum Virtual Machine)
Handles transactions, smart contracts, and state
Maintains the Ethereum trie (accounts, storage)
Provides JSON-RPC APIs for users and dapps
Executes payloads delivered by the consensus layer
Think of it as: “Ethereum before the Merge” — it’s where code executes and gas is spent.

⚖️ CL — Consensus Layer

Examples: Lighthouse, Prysm, Teku, Nimbus, Lodestar
Purpose:
Manages validators and the Beacon Chain
Chooses the canonical chain via Proof of Stake (finality, attestations, fork choice)
Talks to the EL through the Engine API (usually over a JWT-authenticated HTTP port)
Coordinates block proposals and attestations
Think of it as: The “brain” that decides which blocks from EL are valid and in what order.

👤 VL — Validator Client / Validator Layer

Examples:
Built into or bundled with CLs (e.g. lighthouse bn + lighthouse vc)
External validator managers (e.g. validator, validator_client)
Purpose:
Holds validator keys and signs blocks/attestations
Communicates with the CL (not directly with EL)
Can be multiple VCs connecting to one CL instance
Think of it as: The “operator” that actually stakes and produces blocks/attestations on behalf of validators.