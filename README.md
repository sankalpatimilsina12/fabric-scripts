# Fabric Example Scripts

Scripts are subject to change and do not guarantee to work.
They are suppose to provide basic usage information.

1. Fileserver is the NDN producer. Provided by @yoursunny.
2. NDNc is the NDN consumer


## Usage
1. Run fileserver: `python fileserver.py`

2. Run NDNc: `python ndnc.py`

3. Once fileserver and ndnc are both running on the FABRIC nodes, we need to create UDP faces in both directions between the NDN-DPDK forwarders on the two nodes.

4. To create UDP face on the NDN-DPDK forwarder on the fileserver node:
    -  ssh into the fileserver node
    - Create UDP face towards NDNc node. To do this create a file called `face.sh` with the following content:
        ```
        #!/bin/bash
        $FACEID=$(jq -n '{
            scheme: "udp",
            remote: "<remote_ip>:<remote_port>",
        }' | ndndpdk-ctrl --gqlserver http://127.0.0.1:3030 create-face | tee /dev/stderr | jq -r .id)
        ```
        The `<remote_ip>` and `<remote_port>` should be replaced with the IP address and port of the NDNc node where the NDN-DPDK forwarder is running.
    - Make the file executable: `chmod +x face.sh`
    - Run the script: `./face.sh`. This will create a UDP face towards the NDNc node.

5. To create UDP face and register fib on the NDN-DPDK forwarder on the NDNc node:
    -  ssh into the NDNc node
    - Create UDP face and register fib towards fileserver node. To do this create a file called `face_fib.sh` with the following content:
        ```
        #!/bin/bash
        $FACEID=$(jq -n '{
            scheme: "udp",
            remote: "<remote_ip>:<remote_port>",
        }' | ndndpdk-ctrl --gqlserver http://127.0.0.1:3030 create-face | tee /dev/stderr | jq -r .id)

        ndndpdk-ctrl --gqlserver http://127.0.0.1:3030 insert-fib \
        ```
        --name /<fileserver_prefix> --nh $FACEID
        The `<remote_ip>` and `<remote_port>` should be replaced with the IP address and port of the fileserver node where the NDN-DPDK forwarder is running. The `<fileserver_prefix>` should be replaced with the prefix of the fileserver node.
    - Make the file executable: `chmod +x face_fib.sh`
    - Run the script: `./face_fib.sh`. This will create a UDP face and register a fib entry towards the fileserver node.

6. Now we can run the NDNc client to fetch the file from the fileserver node with:
    ```
    sudo docker run -it --rm --network=host \
       	--privileged   --mount type=bind,source=/dev/hugepages,target=/dev/hugepages \
        --mount type=volume,source=run-ndn,target=/run/ndn \
      	sankalpatimilsina/ndnc:may-10-2022 \
        ./sandie-ndn/build/ndncftclient --gqlserver http://127.0.0.1:3030 --pipeline-type aimd \
        --name-prefix /<fileserver_prefix> --copy /<file_name>
    ```
    The `<fileserver_prefix>` should be replaced with the prefix of the fileserver node. The `<file_name>` should be replaced with the name of the file to be fetched from the fileserver node.