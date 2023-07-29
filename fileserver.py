import json
import shlex
import time
import datetime

from fabrictestbed_extensions.fablib.fablib import \
    FablibManager as fablib_manager

import ndndpdk_common
import v4pub

slice_num = int(time.time())

# FABRIC site to allocate slice; must pick a site with IPv6 management address
SITE = 'SALT'
# NDN-DPDK git repository
NDNDPDK_GIT = ndndpdk_common.DEFAULT_GIT_REPO
# NDN name prefix for the file server
FS_PREFIX = f'/fileserver'
# filesystem path for the file server
FS_PATH = '/srv/fileserver'
# segment length served by the file server
FS_SEGMENTLEN = 6*1024

# no need to change anything below
fablib = fablib_manager()
slice_name = f'fileserver@{slice_num}'
print(slice_name)

slice = fablib.new_slice(name=slice_name)
node = slice.add_node(name='fileserver', site=SITE, cores=12,
                      ram=32, disk=100, image='default_ubuntu_22')
v4pub.prepare(slice, [node.get_name()])
slice.submit()

v4pub.modify(slice)

node = slice.get_node(name='fileserver')
v4pub.enable(slice)

# install packages
node.execute(f'''
    echo 'set enable-bracketed-paste off' | sudo tee -a /etc/inputrc
    sudo hostnamectl set-hostname {node.get_name()}
    {ndndpdk_common.apt_install_cmd(extra_pkgs=['gdb'])}
    sudo loginctl enable-linger {node.get_username()}
    sudo systemctl reboot
''')
slice.wait_ssh(progress=True)

# build and install NDN-DPDK
node.execute(ndndpdk_common.dl_build_cmd(repo=NDNDPDK_GIT))

# set CPU isolation
node.execute(f"""
    {ndndpdk_common.cpuset_cmd(node, instances={
        '127.0.0.1:3030': 6,
        '127.0.0.1:3031': 4,
    })}
    sudo systemctl reboot
""")
slice.wait_ssh(progress=True)

FW_ACTIVATE = {
}

MEMIF_SOCKET, MEMIF_ID = '/run/ndn/fileserver.sock', 1
FW_MEMIF = {
    'scheme': 'memif',
    'socketName': MEMIF_SOCKET,
    'id': MEMIF_ID,
    'role': 'server',
}
FS_ACTIVATE = {
    'face': {
        'scheme': 'memif',
        'socketName': MEMIF_SOCKET,
        'id': MEMIF_ID,
        'role': 'client',
    },
    'fileServer': {
        'mounts': [
            {'prefix': FS_PREFIX, 'path': FS_PATH}
        ],
        'segmentLen': FS_SEGMENTLEN,
    },
}

# start NDN-DPDK forwarder, prefix registration service, and fileserver
node.execute(f'''
    sudo mkdir -p {shlex.quote(FS_PATH)}
    sudo chown {node.get_username()} {shlex.quote(FS_PATH)}
    truncate -s 1M {shlex.quote(f'{FS_PATH}/1M.bin')}
    truncate -s 10M {shlex.quote(f'{FS_PATH}/10M.bin')}
    truncate -s 100M {shlex.quote(f'{FS_PATH}/100M.bin')}
    truncate -s 300M {shlex.quote(f'{FS_PATH}/300M.bin')}
    truncate -s 500M {shlex.quote(f'{FS_PATH}/500M.bin')}
    truncate -s 800M {shlex.quote(f'{FS_PATH}/800M.bin')}
    truncate -s 1G {shlex.quote(f'{FS_PATH}/1G.bin')}
    truncate -s 2G {shlex.quote(f'{FS_PATH}/2G.bin')}
    
    # configure gdb
    sudo mkdir -p /root/.config/gdb
    sudo touch /root/.config/gdb/gdbinit
    echo "add-auto-load-safe-path /usr/local/go/src/runtime/runtime-gdb.py" | sudo tee /root/.config/gdb/gdbinit > /dev/null

    CTRL_FW='ndndpdk-ctrl --gqlserver http://127.0.0.1:3030/'
    CTRL_FS='ndndpdk-ctrl --gqlserver http://127.0.0.1:3031/'
    systemctl --user stop nfdreg || true
    sudo $CTRL_FW systemd stop || true
    sudo $CTRL_FS systemd stop || true

    {ndndpdk_common.hugepages_cmd(size=18)}

    sudo $CTRL_FW systemd start
    echo {shlex.quote(json.dumps(FW_ACTIVATE))} | $CTRL_FW activate-forwarder
    
    FW_MEMIF_FACE=$(echo {shlex.quote(json.dumps(FW_MEMIF))} | $CTRL_FW create-face)
    echo $FW_MEMIF_FACE
    $CTRL_FW insert-fib --name {shlex.quote(FS_PREFIX)} --nh $(echo $FW_MEMIF_FACE | jq -r .id)

    sudo $CTRL_FS systemd start
    echo {shlex.quote(json.dumps(FS_ACTIVATE))} | $CTRL_FS activate-fileserver

''')

print(node.get_ssh_command())
print(f'''
----------------------------------------------------------------
NDN-DPDK fileserver is ready.
''')

# Extend lease
print('Extending lease to 2 weeks....')
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
