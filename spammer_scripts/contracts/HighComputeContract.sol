// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

/// @notice Gas-expensive contract that focuses on CPU + memory usage
///         instead of heavy storage writes. For local / test networks only.
contract HighComputeContract {
    // Used to prevent optimizer from pruning work and to carry results across calls.
    uint256 public sink;

    event ComputeWork(bytes32 finalHash, uint256 iterations, uint256 arraySize, uint256 sinkValue);

    /// @notice Burns gas by:
    ///         - Allocating a large memory array (memory expansion)
    ///         - Running tight nested loops
    ///         - Repeated KECCAK256 hashing over changing data
    ///
    /// @param iterations  Outer loop count (CPU emphasis).
    /// @param arraySize   Size of the in-memory array (memory emphasis).
    function burnCpuAndMemory(uint256 iterations, uint256 arraySize) external {
        require(iterations > 0 && iterations <= 1024, "iterations out of range");
        require(arraySize > 0 && arraySize <= 4096, "arraySize out of range");

        bytes32 h = bytes32(0);
        uint256 acc = sink;

        // Allocate a big chunk of memory once (triggers memory expansion).
        bytes32[] memory data = new bytes32[](arraySize);

        for (uint256 i = 0; i < iterations; ++i) {
            // Fill the array with hashes depending on i, j, and acc.
            for (uint256 j = 0; j < arraySize; ++j) {
                // Heavy hashing work
                h = keccak256(
                    abi.encodePacked(h, acc, i, j, block.timestamp, block.number)
                );
                data[j] = h;

                // Mix into accumulator so the optimizer can't remove this.
                acc ^= uint256(h);
            }

            // Hash the array contents as well (forces reading from memory).
            h = keccak256(abi.encodePacked(h, data, acc));
        }

        // Persist something to storage so that work is observable from outside.
        sink = acc ^ uint256(h);

        emit ComputeWork(h, iterations, arraySize, sink);
    }

    /// @notice A lighter helper that only does hashing without the inner array loop.
    ///         Useful as a lower-gas baseline vs burnCpuAndMemory.
    function burnHashOnly(uint256 iterations) external {
        require(iterations > 0 && iterations <= 500_000, "iterations out of range");

        bytes32 h = bytes32(sink);
        uint256 acc = sink;

        for (uint256 i = 0; i < iterations; ++i) {
            h = keccak256(
                abi.encodePacked(h, acc, i, block.timestamp, block.prevrandao)
            );
            acc ^= uint256(h);
        }

        sink = acc ^ uint256(h);
        emit ComputeWork(h, iterations, 0, sink);
    }
}
