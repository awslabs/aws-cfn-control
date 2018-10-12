#@IgnoreInspection BashAddShebang

#
# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file
# except in compliance with the License. A copy of the License is located at
#
#     http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is distributed on an "AS IS"
# BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under the License.
#


function fix_zfs_repo {
  echo "Fixing ZFS repo..."
  sudo cat /etc/yum.repos.d/zfs.repo  | while read l
  do
    if [ "$l" == "[zfs]" ]; then
      let on_zfs=1
    elif [ "$l" == "[zfs-kmod]" ]; then
      let on_zfs_kmod=1
    fi
    if [[ "$on_zfs" -eq 1 ]] && [[ "$l" == "enabled=1" ]]; then
      l="enabled=0"
      let on_zfs=0
    elif [[ "$on_zfs_kmod" -eq 1 ]] &&  [[ "$l" == "enabled=0" ]]; then
      l="enabled=1"
      let on_zfs_kmod=0
    fi
    echo $l
  done > /tmp/new_zfs.repo
  sudo cp /etc/yum.repos.d/zfs.repo /etc/yum.repos.d/zfs.repo.dist
  sudo mv /tmp/new_zfs.repo /etc/yum.repos.d/zfs.repo
  echo "Done fixing ZFS repo"

}

function zfs_install {
  echo -n "Fixing and Re-Installing ZFS..."
  known_zfs_key="C93AFFFD9F3F7B03C310CEB6A9D5A1C0F14AB620"
  sudo yum -y remove zfs zfs-kmod spl spl-kmod libzfs2 libnvpair1 libuutil1 libzpool2 zfs-release
  sudo yum -y install http://download.zfsonlinux.org/epel/zfs-release.el7_5.noarch.rpm
  actual_zfs_key=$(gpg --quiet --with-fingerprint /etc/pki/rpm-gpg/RPM-GPG-KEY-zfsonlinux | grep "Key fingerprint" | cut -d"=" -f2 | tr -d ' ')
  echo "Checking keys..."
  if [[ "$known_zfs_key" != "$actual_zfs_key" ]]; then
    echo "ERROR: ZFS installation keys not valid!!!"
    echo "Exiting..."
    exit
  fi
  fix_zfs_repo
  sudo yum -y autoremove
  sudo yum -y clean metadata
  sudo yum -y install zfs
  echo "Done installing ZFS"
}

function zfs_create {
  sudo /sbin/modprobe zfs
  modinfo zfs
  sudo zpool create -O compression=lz4 -O atime=off -O sync=disabled -f ${zfs_pool_name} -o ashift=12 xvdh xvdi xvdj xvdk xvdl xvdm
  sudo zpool status -v
  sudo zfs create ${zfs_pool_name}/${zfs_mount_point}
}

function zfs_startup {
  sudo systemctl enable zfs-import-cache
  sudo systemctl enable zfs-mount.service
  sudo systemctl enable zfs.target
}

dev_count=0
function ck_devs {
  devs_ready=0
  for l in {h..m}; do
    if [[ ! -b /dev/xvd${l} ]]; then
      devs_ready=0
      ((dev_count = $dev_count + 1))
      if [[ $dev_count -gt 30 ]]; then
        echo "Devices not ready, exiting..."
        exit
      else
        sleep 10
        ck_devs
      fi
    else
      devs_ready=1
    fi
  done
  echo "Devices ready."
}

function nfs_server_settings {
  sudo su -c 'echo -e "STATD_PORT=\"32765\"\nSTATD_OUTGOING_PORT=\"32766\"\nSTATDARG=\"-p 32765 -o 32766\"\nMOUNTD_PORT=\"32767\"\nRPCMOUNTDOPTS=\"-p 32767\"
LOCKD_UDPPORT=\"32768\"\nLOCKD_TCPPORT=\"32768\"\nRQUOTAD_PORT=\"32769\"\nRQUOTAD=\"no\"\nRPCNFSDCOUNT=\"128\""' > /etc/sysconfig/nfs
}

function nfs_config {
  nfs_server_settings
  sudo su -c 'echo "'"${zfs_pool_name}/${zfs_mount_point} ${nfs_cidr_block}${nfs_opts}"'" > /etc/exports'
  sudo systemctl enable rpcbind
  sudo systemctl enable nfs-server
  sudo systemctl start rpcbind
  sudo systemctl start nfs-server
  sudo systemctl start rpc-statd
  showmount -e localhost
}

function inst_updates {
  echo "Installing updates"
  sudo yum install nfs-utils rpcbind -y
  sudo yum install -y vim
  sudo yum update -y
  echo "Updates complete"
}

function ck_status {
  zfs_status=$(sudo zpool status | grep state | awk {'print $2'})
  sudo mount | grep ${zfs_pool_name}
  let zfs_mount_rc=$?
  sudo showmount -e localhost | grep -v Export | grep ${zfs_mount_point}
  let nfs_status_rc=$?
  if [[ "$zfs_status" == "ONLINE" ]] && [[ "$nfs_status_rc" -eq 0 ]] && [[ "$zfs_mount_rc" -eq 0 ]]; then
    echo "ZFS and NFS installed and configured"
    curl -X PUT -H 'Content-Type:' --data-binary '{ "Status" : "SUCCESS",  "Reason" : "ZFS and NFS installed and configured",  "UniqueId" : "ZFS001",  "Data" : "ZFS and NFS installed and configured."}'  "${my_wait_handle}"
  fi
}

while [[ ! $devs_ready ]]; do
  ck_devs
done
inst_updates
zfs_install
zfs_create
zfs_startup
nfs_config
ck_status


