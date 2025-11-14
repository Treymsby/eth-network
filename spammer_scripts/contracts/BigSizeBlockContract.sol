// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

/// @notice For LOCAL / PRIVATE networks only.
///         Tries to maximize block size (in bytes) by:
///         - Accepting very large calldata
///         - Re-emitting it many times as log data
///         - Optionally writing to storage
contract BlockSizeMaximizer {
    uint256 public sink;
    mapping(uint256 => bytes32) public spam;

    /// @dev No indexed topics = cheaper gas per data byte.
    event HugePayload(bytes data);

    /// @notice Most byte-dense option:
    ///         - You send a very large `payload` in calldata.
    ///         - The contract re-emits it `logCount` times as event data.
    ///
    /// @param payload   Big calldata blob (ideally lots of 0x00 bytes).
    /// @param logCount  How many times to re-emit `payload` in logs.
    function spamLogs(bytes calldata payload, uint256 logCount) external {
        require(payload.length > 0, "payload empty");
        require(logCount > 0, "logCount 0");

        bytes32 acc = bytes32(sink);

        for (uint256 i = 0; i < logCount; ++i) {
            emit HugePayload(payload);
            // Tiny bit of work so the optimizer cannot drop the loop.
            acc = keccak256(abi.encodePacked(acc, payload.length, i));
        }

        sink = uint256(acc);
    }

    /// @notice Same as `spamLogs` but also does storage writes.
    ///         This increases chain state size in addition to logs.
    ///
    /// @param payload       Big calldata blob.
    /// @param logCount      Number of log emissions.
    /// @param storageSlots  Number of storage slots to write.
    function spamLogsAndStorage(
        bytes calldata payload,
        uint256 logCount,
        uint256 storageSlots
    ) external {
        require(payload.length > 0, "payload empty");
        require(logCount > 0, "logCount 0");
        require(storageSlots > 0, "storageSlots 0");

        bytes32 acc = bytes32(sink);

        // 1) Log spam (big receipts, lots of bytes in the block)
        for (uint256 i = 0; i < logCount; ++i) {
            emit HugePayload(payload);
            acc = keccak256(abi.encodePacked(acc, payload.length, i));
        }

        // 2) Storage spam (expands state; heavy gas)
        for (uint256 j = 0; j < storageSlots; ++j) {
            bytes32 v = keccak256(abi.encodePacked(acc, j, block.number));
            spam[j + 1] = v; // small, fixed set of keys; can be reused
            acc ^= v;
        }

        sink = uint256(acc);
    }

    /// @notice "Auto" mode: keeps emitting logs until near out-of-gas.
    ///         Less predictable, but tries to burn almost all gas in one call.
    ///
    /// @dev Pick `payload` size based on your tx gasLimit.
    function autoFill(bytes calldata payload) external {
        require(payload.length > 0, "payload empty");

        bytes32 acc = bytes32(sink);
        uint256 i;

        // Leave a safety margin so we don't revert with out-of-gas.
        // Very conservative; you can lower the threshold after testing.
        while (gasleft() > 200_000) {
            emit HugePayload(payload);
            acc = keccak256(abi.encodePacked(acc, payload.length, i));
            unchecked {
                ++i;
            }
        }

        sink = uint256(acc);
    }
}
