// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

/// @notice Low-gas transaction spam contract.
///         Each call is a valid tx but does almost nothing:
///         just emits a tiny event. Perfect for high-TPS spam
///         with minimal gas per tx on a testnet.
contract LowGasSpamContract {
    /// @dev Minimal event: 1 indexed topic (sender) + 1 small value.
    event Spam(address indexed sender, uint64 tag);

    /// @notice Cheapest spam entry point.
    /// @param tag Arbitrary small number (e.g. random, counter from the spammer).
    ///            Lets you distinguish txs in logs if needed.
    function spam(uint64 tag) external {
        // No storage writes, no loops, no hashing – just an event.
        emit Spam(msg.sender, tag);
    }

    /// @notice Slightly more expensive variant:
    ///         emits multiple events in a single tx (still no storage).
    ///         Use only if you want to compare "many tx" vs "more work per tx".
    function multiSpam(uint64[] calldata tags) external {
        for (uint256 i = 0; i < tags.length; ++i) {
            emit Spam(msg.sender, tags[i]);
        }
    }
}
