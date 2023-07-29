import datetime
import os
import json
import time
import shlex
import v4pub
import v4wg
import sys

from fabrictestbed_extensions.fablib.fablib import \
FablibManager as fablib_manager

slice_num = int(time.time())

SITE = 'DALL'

fablib = fablib_manager()
slice_name = f'ndnc@{slice_num}'
print(slice_name)

print('Creating new slice....')
slice = fablib.new_slice(name=slice_name)
node = slice.add_node(name='ndnc', site=SITE, cores=12,
                       ram=32, disk=80, image='default_ubuntu_22')
v4pub.prepare(slice, [node.get_name()])
slice.submit()

v4pub.modify(slice)

node = slice.get_node(name='ndnc')
v4pub.enable(slice)

print('Installing packages....')
# Install Packages
node.execute(f'''
    sudo hostnamectl set-hostname {node.get_name()}
    echo "deb [arch=amd64 trusted=yes] https://nfd-nightly-apt.ndn.today/ubuntu jammy main" | sudo tee /etc/apt/sources.list.d/nfd-nightly.list
    sudo apt update
    sudo DEBIAN_FRONTEND=noninteractive apt full-upgrade -y
    sudo DEBIAN_FRONTEND=noninteractive apt install -y --no-install-recommends jq libibverbs-dev linux-image-generic ndnsec ndnpeek nfd
    sudo loginctl enable-linger {node.get_username()}
    
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list
    sudo apt update
    sudo DEBIAN_FRONTEND=noninteractive apt install -y --no-install-recommends docker-ce
    sudo loginctl enable-linger {node.get_username()}
    
    sudo groupadd docker
    sudo usermod -aG docker $USER
    newgrp docker
    docker logout
    jq -n '{{
      "data-root": "/home/docker",
      "log-driver": "local",
      "log-opts": {{
        "max-size": "10m",
        "max-file": "3"
      }},
      "mtu": 1420,
      "dns": ["1.1.1.1"]
    }}' | sudo tee /etc/docker/daemon.json
    sudo systemctl restart docker
    
    wget https://raw.githubusercontent.com/DPDK/dpdk/main/usertools/dpdk-hugepages.py
    chmod +x dpdk-hugepages.py
    sudo mv dpdk-hugepages.py /usr/bin/
    
    sudo reboot
''')
slice.wait_ssh(progress=True)

print('Pulling docker images for ndn-dpdk and ndnc....')
node.execute('''
    docker pull sankalpatimilsina/ndnc:nov-11
    docker pull sankalpatimilsina/ndn-dpdk-apr-27:latest
    docker tag sankalpatimilsina/ndn-dpdk-apr-27 ndn-dpdk
''')

print('Setting forwarder args....')
# Set NDN-DPDK Forwarder args
FW_ACTIVATE = {
    'mempool': {
        'DIRECT': {'capacity': 2**20-1, 'dataroom': 9200},
        'INDIRECT': {'capacity': 2**21-1},
    },
}


print('Running forwarder....')
# Run NDN-DPDK Forwarder and NDNc
node.execute(f'''
    sudo dpdk-hugepages.py --clear
    sudo dpdk-hugepages.py --pagesize 1G --setup 30G
    
    echo "Launching forwarder container...."
    sudo docker ps -q --filter "name=fw" | grep -q . && sudo docker stop fw
    sudo docker ps -q -a --filter "name=fw" | grep -q . && sudo docker rm fw
    
    sudo docker run -d --name fw \
          --network host \
          --privileged \
          --mount type=bind,source=/dev/hugepages,target=/dev/hugepages \
          --mount type=volume,source=run-ndn,target=/run/ndn \
          ndn-dpdk

    sleep 5
    
    echo "Activating forwarder...."
    echo {shlex.quote(json.dumps(FW_ACTIVATE))} | sudo docker run -i --rm \
    --privileged \
    --network host \
    --mount type=bind,source=/dev/hugepages,target=/dev/hugepages \
    --mount type=volume,source=run-ndn,target=/run/ndn \
    ndn-dpdk ndndpdk-ctrl activate-forwarder
''')

print('Extending lease to 2 weeks....')
# Extend lease
end_date = (datetime.datetime.now(datetime.timezone.utc) +
            datetime.timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S %z")
try:
    slice = fablib.get_slice(name=slice_name)

    slice.renew(end_date)
except Exception as e:
    print(f"Exception: {e}")
try:
    slice = fablib.get_slice(name=slice_name)
    print(f"Lease End (UTC): {slice.get_lease_end()}")
except Exception as e:
    print(f"Exception: {e}")

# Delete Slice
# try:
#     slice = fablib.get_slice(name=slice_name)
#     slice.delete()
# except Exception as e:
#     print(f"Fail: {e}")
