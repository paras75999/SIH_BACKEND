// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract Anchor {
    mapping(bytes32 => bool) public anchored;
    event Anchored(bytes32 indexed h, address indexed who, uint256 timestamp);

    function anchor(bytes32 h) external {
        anchored[h] = true;
        emit Anchored(h, msg.sender, block.timestamp);
    }

    function isAnchored(bytes32 h) external view returns (bool) {
        return anchored[h];
    }
}
