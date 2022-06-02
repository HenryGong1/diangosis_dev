#!/bin/sh
waitfor /data/SN 20
cp /data/SN /home/SN
if [ -f /opt/setup.sh ]; then
    . /opt/setup.sh j7-l4e
    hamlaunch stop
    sh /opt/plusai/launch/j7-l4e/stop-all.sh
fi

ps -A -o "pid,args" | grep opt | grep -v grep | awk  '{print $1}' | xargs kill -9
sleep 30
# mount /data for nvdriveupdate_server
df -h | grep vblk_ufs10 | grep data
if [ $? != 0 ]; then
    echo "/data is not mounted"
    mount -t qnx6 -omntperms=0777,mntuid=3360,mntgid=3360 /dev/vblk_ufs10 /data
    if [ $? != 0 ]; then
        echo "cannot mount ufs10, format"
        (echo "y") | mkqnx6fs /dev/vblk_ufs10
        sleep 30
        mount -t qnx6 -omntperms=0777,mntuid=3360,mntgid=3360 /dev/vblk_ufs10 /data
        if [ $? != 0 ]; then
            echo "cannot mount ufs10 for nvidia_driveupdate"
            exit 1
        fi
    fi
else
    ls -l / | grep data | grep nvdriveupdate_server
    if [ $? != 0 ]; then
      echo "remount /data for nvidia update server"
      umount /data
      if [ $? != 0 ]; then
          echo "cannot umount ufs10"
          exit 1
      fi
      mount -t qnx6 -omntperms=0777,mntuid=3360,mntgid=3360 /dev/vblk_ufs10 /data
      if [ $? != 0 ]; then
          echo "cannot mount ufs10 for nvidia_driveupdate"
          exit 1
      fi
    fi
fi
cp /home/SN /data/SN
cd /home/plusai
cp /data/doip_uds_flash/flash_log.txt /home/plusai/flash_log.txt
rm -rf /data/doip_uds_flash
mkdir -p /data/doip_uds_flash
tar zxf /home/plusai/uds_server_package.tar.xz -C /
cp /home/plusai/flash_log.txt /data/doip_uds_flash
sleep 10
nohup /usr/local/driveupdate/start_du_service.sh 2>/dev/null 1>/dev/null &

set -e
export LD_LIBRARY_PATH=/opt/plusai/lib:/opt/plusai/external/opt/lib:$LD_LIBRARY_PATH
nohup /opt/plusai/lib/doip_uds_flash/doip_uds_flash_server_node -port=13400 2>/dev/null 1>/dev/null &
