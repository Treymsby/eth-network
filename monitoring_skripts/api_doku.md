# DORA API: 
## SLOTs: Returns a list of slots with various filtering options, sorted by slot number descending
- http://127.0.0.1:35004/api/v1/slots
- Returns:
    {
    "data": {
        "next_slot": 0,
        "slots": [
        {
            "attestation_count": 0,
            "attester_slashing_count": 0,
            "avg_exec_time": 0,
            "blob_count": 0,
            "block_root": "string",
            "block_size": 0,
            "deposit_count": 0,
            "el_extra_data": "string",
            "epoch": 0,
            "eth_block_number": 0,
            "eth_transaction_count": 0,
            "execution_times": [
            {
                "avg_time": 0,
                "client_type": "string",
                "count": 0,
                "max_time": 0,
                "min_time": 0
            }
            ],
            "exit_count": 0,
            "finalized": true,
            "gas_limit": 0,
            "gas_used": 0,
            "graffiti": "string",
            "graffiti_text": "string",
            "is_mev_block": true,
            "max_exec_time": 0,
            "mev_block_relays": "string",
            "min_exec_time": 0,
            "parent_root": "string",
            "proposer": 0,
            "proposer_name": "string",
            "proposer_slashing_count": 0,
            "recv_delay": 0,
            "scheduled": true,
            "slot": 0,
            "state_root": "string",
            "status": "string",
            "sync_aggregate_participation": 0,
            "time": "string",
            "with_eth_block": true
        }
        ],
        "total_count": 0
    },
    "status": "string"
    }
## Blocks: Returns a list of MEV blocks with relay information and comprehensive filtering
- http://127.0.0.1:35004/api/v1/mev_blocks
- Returns:

## Epochs: Returns a list of epochs with detailed information and statistics
- http://127.0.0.1:35004/api/v1/epochs
- Returns:
    {
    "data": {
        "current_epoch": 0,
        "epoch_count": 0,
        "epochs": [
        {
            "attestations": 0,
            "attester_slashings": 0,
            "bls_changes": 0,
            "consolidation_requests": 0,
            "deposits": 0,
            "deposits_amount": 0,
            "eligible_ether": 0,
            "epoch": 0,
            "exits": 0,
            "finalized": true,
            "head_voted": 0,
            "max_sync_committee_size": 0,
            "min_sync_committee_size": 0,
            "missed_blocks": 0,
            "orphaned_blocks": 0,
            "proposed_blocks": 0,
            "proposer_slashings": 0,
            "sync_participation": 0,
            "target_voted": 0,
            "total_voted": 0,
            "validator_balance": 0,
            "validators": 0,
            "vote_participation": 0,
            "voting_finalized": true,
            "voting_justified": true,
            "withdrawal_requests": 0,
            "withdrawals_amount": 0,
            "withdrawals_count": 0
        }
        ],
        "finalized_epoch": 0,
        "first_epoch": 0,
        "last_epoch": 0,
        "total_epochs": 0
    },
    "status": "string"
    }

b

# Spamoor:
## Returns comprehensive graphs data for the dashboard including all spammers, totals, and time-series data
- http://127.0.0.1:35000/api/graphs/dashboard
- Response:
    {
  "data": [
    {
      "blocks": 0,
      "endBlock": 0,
      "othersGas": 0,
      "spammers": {
        "additionalProp1": {
          "confirmed": 0,
          "gas": 0,
          "pending": 0,
          "submitted": 0
        },
        "additionalProp2": {
          "confirmed": 0,
          "gas": 0,
          "pending": 0,
          "submitted": 0
        },
        "additionalProp3": {
          "confirmed": 0,
          "gas": 0,
          "pending": 0,
          "submitted": 0
        }
      },
      "startBlock": 0,
      "totalGas": 0,
      "ts": "string"
    }
  ],
  "others": {
    "gasUsed": 0
  },
  "range": {
    "end": "string",
    "start": "string"
  },
  "spammers": [
    {
      "confirmed": 0,
      "gasUsed": 0,
      "id": 0,
      "name": "string",
      "pending": 0,
      "status": 0,
      "submitted": 0,
      "updated": "string"
    }
  ],
  "totals": {
    "confirmed": 0,
    "gasUsed": 0,
    "pending": 0,
    "submitted": 0
  }
}

# Promethues API
http://127.0.0.1:35006/api/...

# Blockscout
# st