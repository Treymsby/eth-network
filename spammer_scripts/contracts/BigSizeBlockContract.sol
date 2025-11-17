// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;
contract BigSizeBlockContract {
    /// @param padding Arbitrary bytes used purely to increase tx / block size.
    function padBlock(bytes calldata padding) external pure {
        // Intentionally left blank:
        // - No storage
        // - No events/logs
        // - No memory copies
        // Just here so the compiler thinks we used the variable.
        padding;
    }

    /// @param padding Arbitrary bytes used purely to increase tx / block size.
    function padBlockPayable(bytes calldata padding) external payable {
        padding;
    }
}
