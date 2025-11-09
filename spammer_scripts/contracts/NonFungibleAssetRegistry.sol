// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract SimpleAssetRegistry {
    struct Asset {
        address owner;
        string metadata;
    }

    uint256 public nextAssetId;
    mapping(uint256 => Asset) public assets;

    event AssetCreated(uint256 indexed assetId, address indexed owner, string metadata);
    event AssetTransferred(uint256 indexed assetId, address indexed from, address indexed to);

    function createAsset(string calldata metadata) external returns (uint256) {
        uint256 assetId = nextAssetId;
        assets[assetId] = Asset({
            owner: msg.sender,
            metadata: metadata
        });
        emit AssetCreated(assetId, msg.sender, metadata);
        nextAssetId++;
        return assetId;
    }

    function transferAsset(uint256 assetId, address newOwner) external {
        Asset storage asset = assets[assetId];
        require(asset.owner == msg.sender, "Only owner can transfer");
        address oldOwner = asset.owner;
        asset.owner = newOwner;
        emit AssetTransferred(assetId, oldOwner, newOwner);
    }

    function getAsset(uint256 assetId) external view returns (address owner, string memory metadata) {
        Asset storage asset = assets[assetId];
        return (asset.owner, asset.metadata);
    }
}
