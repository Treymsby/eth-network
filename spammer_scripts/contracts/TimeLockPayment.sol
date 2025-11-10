// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract TimeLock {
    address public payer;
    address public payee;
    uint256 public releaseTime;
    uint256 public amount;

    event FundsLocked(address indexed payer, uint256 amount, uint256 releaseTime);
    event FundsReleased(address indexed payee, uint256 amount);

    constructor(address _payee, uint256 _releaseTime) payable {
        require(_releaseTime > block.timestamp, "Release time must be in future");
        payer = msg.sender;
        payee = _payee;
        releaseTime = _releaseTime;
        amount = msg.value;
        emit FundsLocked(payer, msg.value, releaseTime);
    }

    function release() public {
        require(block.timestamp >= releaseTime, "Current time is before release time");
        require(msg.sender == payee, "Only payee can release funds");
        uint256 payment = amount;
        amount = 0;
        (bool success, ) = payee.call{value: payment}("");
        require(success, "Transfer failed");
        emit FundsReleased(payee, payment);
    }
}
