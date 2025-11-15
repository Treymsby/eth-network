// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

/// @notice Contract intended for *test / research networks only*.
///         It lets you send very large calldata to bloat block size while
///         doing almost no execution work (minimal extra gas beyond calldata).
contract BigSizeBlockContract {
    /// @notice Accepts arbitrary-length calldata and does absolutely nothing
    ///         with it. The calldata itself is included in the block, so
    ///         you can make blocks large by sending huge `padding` values.
    ///
    /// @param padding Arbitrary bytes used purely to increase tx / block size.
    function padBlock(bytes calldata padding) external pure {
        // Intentionally left blank:
        // - No storage
        // - No events/logs
        // - No memory copies
        // Just here so the compiler thinks we used the variable.
        padding;
    }

    /// @notice Same idea, but marked payable in case you want to also send ETH.
    ///         Still does nothing with the data or the value.
    ///
    /// @param padding Arbitrary bytes used purely to increase tx / block size.
    function padBlockPayable(bytes calldata padding) external payable {
        // Still no-op, but can receive ETH.
        padding;
    }
}
