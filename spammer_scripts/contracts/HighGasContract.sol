pragma solidity ^0.8.26;

contract HighGasContract {
    // State used to force SSTORE and prevent optimizer from pruning work.
    uint256 public sink;
    mapping(uint256 => uint256) public store;

    event DidWork(uint256 indexed i, bytes32 hashResult, uint256 valueWritten);

    /// @notice Burns a lot of gas by doing:
    ///         - SLOAD on a mapping
    ///         - KECCAK256 hashing
    ///         - SSTORE (expensive, especially zero -> non-zero)
    ///         - LOG/emit event
    /// @param iterations Number of loop iterations. Keep it small or tx will OOG.
    function burnGas(uint256 iterations) external {
        // loop with multiple expensive operations.
        for (uint256 i = 0; i < iterations; ++i) {
            // 1) Expensive SLOAD
            uint256 current = store[i];

            // 2) Expensive KECCAK256 hash
            bytes32 h = keccak256(
                abi.encodePacked(
                    current,
                    sink,
                    block.timestamp,
                    block.number,
                    i
                )
            );

            // 3) Expensive SSTORE (zero -> non-zero especially costly)
            uint256 newValue = uint256(h) ^ (current + 1);
            store[i] = newValue;

            // 4) Update global sink so optimizer can't drop the work
            sink ^= newValue;

            // 5) Expensive LOG (event) with topics and data
            emit DidWork(i, h, newValue);
        }
    }

    /// @notice Variant that focuses more on storage churn (lots of SSTORE).
    ///         This can be even nastier for state growth.
    function burnStorageOnly(uint256 iterations) external {
        for (uint256 i = 0; i < iterations; ++i) {
            // Each write to a *new* slot or zero->non-zero costs a lot of gas.
            uint256 newValue = uint256(
                keccak256(abi.encodePacked(i, sink, blockhash(block.number - 1)))
            );

            store[i + sink] = newValue;
            sink += newValue; // keep changing sink so the index and values evolve
        }
    }
}
