Start & Stopping Engine:
sudo kurtosis engine stop
sudo kurtosis engine start

To Start: 
sudo kurtosis run --enclave eth-network github.com/ethpandaops/ethereum-package --args-file network_params.yaml

To Stop: WARNING! STOPPING CANNOT BE STARTED AGAIN.
sudo kurtosis enclave stop eth-network

To Remove:
sudo kurtosis enclave rm eth-network

Inspect Enclave:
sudo kurtosis enclave inspect eth-network

Interact with node:
kurtosis service shell <enclave-name> <node-name>

Inspect your deployed application:
z.b via Browser: http: 4000/tcp -> http://127.0.0.1:32825

--- GUI ---
To look at gui just open dora ip!
z.b http://127.0.0.1:32826 wird bei setup gezeigt.

--- MetaMask ---
Wallet
Password: 8Gst6x7A*+J?Yx'
-- Remix --

FOR PAPER:
If you want to reproduce this do follwoing
1. Start the Network and make sure it stabalizes (SEE Dora Finalizing epochs)

Why 12 Node Pairs:
Idle 5% and Every 12s spike to 60% (Wake Up of node)

