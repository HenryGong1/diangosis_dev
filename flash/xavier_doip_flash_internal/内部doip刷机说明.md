## 仅用于智加内部测试车辆
### 环境
Ubuntu 18.04
### 上位机安装 (首次使用)
在办公室或者厂房plusai WIFI, 公司VPN域名解析有问题, 刷机不需要互联网  
cd 当前目录 `./setup.sh`
### Xavier 刷写
1. 向晨笛团队索要内部测试刷机包 如: `l4e-phase1-p1.1_master_1991_dec-flash-images.tar.xz`
2. 把XXXXXX_dec-flash-images.tar.xz 移动到该文件夹并重命名(`xavier_doip_flash_internal`) `dec-flash-images.tar.xz`
3. `./prepare_image.sh` 生成 `flash-images.tar.xz` (每个版本只需运行一次)
4. ADU 开机
5. 上位机网线连到ADU e3495 或者 路由器
6. 确认 `ping 192.168.11.100` 成功
7. (本车首次doip刷机) 确认ADU BSP版本 5.2.3 ssh登录ADU `cat /usr/libnvidia/version-pdk.txt`
8. 上位机 cd 当前目录 `./flash.sh`
9. 正常刷机耗时约30分钟, ADU会重启2次
10. 遇到问题可以把当前目录中doip_flash_*.log 发给晨笛团队
