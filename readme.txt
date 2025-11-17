To Remove:
sudo kurtosis enclave rm eth-network

Inspect Enclave:
sudo kurtosis enclave inspect eth-network

Interact with node:
kurtosis service shell <enclave-name> <node-name>

To Start:
sudo kurtosis engine restart
sudo kurtosis run --enclave eth-network github.com/ethpandaops/ethereum-package --args-file network_parameters_files/network_geth_lighthouse.yaml 

To Stop
sudo kurtosis enclave stop eth-network
sudo kurtosis enclave rm eth-network
sudo kurtosis engine restart

To start python venv:
source .venv/bin/activate