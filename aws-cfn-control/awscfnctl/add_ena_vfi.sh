#!/bin/bash -x

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

ena_version="1.2.0"
vfi_version="4.2.1"

function create_vfi_dkms_file {

touch /usr/src/ixgbevf-${vfi_version}/dkms.conf

cat << EOF >> /usr/src/ixgbevf-${vfi_version}/dkms.conf
PACKAGE_NAME="ixgbevf"
PACKAGE_VERSION=$vfi_version
CLEAN="cd src/; make clean"
MAKE="cd src/; make BUILD_KERNEL=\${kernelver}"
BUILT_MODULE_LOCATION[0]="src/"
BUILT_MODULE_NAME[0]="ixgbevf"
DEST_MODULE_LOCATION[0]="/updates"
DEST_MODULE_NAME[0]="ixgbevf"
AUTOINSTALL="yes"
EOF

}

function create_ena_dkms_file {

touch /usr/src/amzn-drivers-${ena_version}/dkms.conf

cat << EOF >> /usr/src/amzn-drivers-${ena_version}/dkms.conf
PACKAGE_NAME="ena"
PACKAGE_VERSION="$ena_version"
CLEAN="make -C kernel/linux/ena clean"
MAKE="make -C kernel/linux/ena/ BUILD_KERNEL=\${kernelver}"
BUILT_MODULE_NAME[0]="ena"
BUILT_MODULE_LOCATION="kernel/linux/ena"
DEST_MODULE_LOCATION[0]="/updates"
DEST_MODULE_NAME[0]="ena"
AUTOINSTALL="yes"
EOF

}

function build_inst_vfi {

  pushd /tmp
  curl -O  https://s3.amazonaws.com/${bucket}/ixgbevf-${vfi_version}.tar.gz
  tar -xvf ixgbevf-${vfi_version}.tar.gz
  sudo mv ixgbevf-${vfi_version} /usr/src

  create_vfi_dkms_file

  sudo dkms add -m ixgbevf -v $vfi_version
  sudo dkms build -m ixgbevf -v $vfi_version
  sudo dkms install -m ixgbevf -v $vfi_version

  popd

}

function build_inst_ena {

  pushd /tmp
  if [[ ! -d amzn-drivers ]]; then
    git clone https://github.com/amzn/amzn-drivers
  fi

  sudo mv amzn-drivers /usr/src/amzn-drivers-${ena_version}

  create_ena_dkms_file

  sudo dkms add -m amzn-drivers -v $ena_version
  sudo dkms build -m amzn-drivers -v $ena_version
  sudo dkms install -m amzn-drivers -v $ena_version

  popd
}

function fix_net_dev_names {

  sudo sed -i '/^GRUB\_CMDLINE\_LINUX/s/\"$/\ net\.ifnames\=0\"/' /etc/default/grub
  sudo grub2-mkconfig -o /boot/grub2/grub.cfg

}

function install_reqs {

  sudo yum install "kernel-devel-uname-r == $(uname -r)"  -y
  sudo yum install vim git gcc dkms -y

}

function ck_os {

  os=$(cat /etc/redhat-release  | awk {'print $1'} | tr '[A-Z]' '[a-z]')

}

function ck_status {

  vfi_status=$(sudo dkms -m ixgbevf status | grep installed)
  ena_status=$(sudo dkms -m amzn-drivers status | grep installed)

  if [[ "$vfi_status" ]]; then
    echo "VFI (ixdbevf) drivers are installed"
  else
    echo "VFI (ixdbevf) drivers are NOT installed"
  fi

  if [[ "$ena_status" ]]; then
    echo "ENA (amzn-drivers) drivers are installed"
  else
    echo "ENA (amzn-drivers) drivers are NOT installed"
  fi

}


install_reqs
build_inst_ena
build_inst_vfi
fix_net_dev_names
sudo depmod
ck_status


