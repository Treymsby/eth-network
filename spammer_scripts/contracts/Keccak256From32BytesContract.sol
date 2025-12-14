// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

library Keccak256From32BytesLib {
    function keccak256From32Bytes(bytes32 input) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked(input));
    }
}

