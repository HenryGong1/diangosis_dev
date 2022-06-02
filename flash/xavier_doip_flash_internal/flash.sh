#!/bin/bash
set -e
export ADU_ROOT_PASSWORDS="PLAV2021! plav=nb! root"
export IMAGE_KEY_PATH="$(pwd)/image_key"
export KEY=`cat $IMAGE_KEY_PATH`
export IMAGE_PATH="$(pwd)/flash-images.tar.xz"
export IMAGE_CHECKSUM=`cksum ${IMAGE_PATH} | awk '{split($0, a, " "); print a[1] }'`
export UDS_CLIENT_PATH="$(pwd)/doip_uds_flash_client"
export LD_LIBRARY_PATH="$(pwd)/lib:$LD_LIBRARY_PATH"
rm -rf uds_server_package.tar.xz
source venv/bin/activate
python3 doip_flash.py $1
