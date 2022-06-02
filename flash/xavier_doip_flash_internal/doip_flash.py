#!/usr/bin/python3

import paramiko
import sys
import os
import subprocess
from typing import Tuple
import re
import jsonpickle
import logging
import signal
from scp import SCPClient
from multiprocessing import JoinableQueue, Process
import queue
import time
import argparse
import time
import datetime
from datetime import timedelta
from datetime import datetime
from alive_progress import alive_bar
import shutil

# Logging formatter supporting colored output
class LogFormatter(logging.Formatter):

    COLOR_CODES = {
        logging.CRITICAL: "\033[1;35m", # bright/bold magenta
        logging.ERROR:    "\033[1;31m", # bright/bold red
        logging.WARNING:  "\033[0;92m", # bright/bold green
        logging.INFO:     "\033[0;37m", # white / light gray
        logging.DEBUG:    "\033[1;30m"  # bright/bold black / dark gray
    }

    RESET_CODE = "\033[0m"

    def __init__(self, color, *args, **kwargs):
        super(LogFormatter, self).__init__(*args, **kwargs)
        self.color = color

    def format(self, record, *args, **kwargs):
        if (self.color == True and record.levelno in self.COLOR_CODES):
            record.color_on  = self.COLOR_CODES[record.levelno]
            record.color_off = self.RESET_CODE
        else:
            record.color_on  = ""
            record.color_off = ""
        return super(LogFormatter, self).format(record, *args, **kwargs)

# Setup logging
def setup_logging(console_log_output, console_log_level, console_log_color, logfile_file, logfile_log_level, logfile_log_color, log_line_template):

    # Create logger
    # For simplicity, we use the root logger, i.e. call 'logging.getLogger()'
    # without name argument. This way we can simply use module methods for
    # for logging throughout the script. An alternative would be exporting
    # the logger, i.e. 'global logger; logger = logging.getLogger("<name>")'
    logger = logging.getLogger()

    # Set global log level to 'debug' (required for handler levels to work)
    logger.setLevel(logging.DEBUG)

    # Create console handler
    console_log_output = console_log_output.lower()
    if (console_log_output == "stdout"):
        console_log_output = sys.stdout
    elif (console_log_output == "stderr"):
        console_log_output = sys.stderr
    else:
        print("Failed to set console output: invalid output: '%s'" % console_log_output)
        return False
    console_handler = logging.StreamHandler(console_log_output)

    # Set console log level
    try:
        console_handler.setLevel(console_log_level.upper()) # only accepts uppercase level names
    except:
        print("Failed to set console log level: invalid level: '%s'" % console_log_level)
        return False

    # Create and set formatter, add console handler to logger
    console_formatter = LogFormatter(fmt=log_line_template, color=console_log_color)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # Create log file handler
    try:
        logfile_handler = logging.FileHandler(logfile_file, 'w+')
    except Exception as exception:
        print("Failed to set up log file: %s" % str(exception))
        return False

    # Set log file log level
    try:
        logfile_handler.setLevel(logfile_log_level.upper()) # only accepts uppercase level names
    except:
        print("Failed to set log file log level: invalid level: '%s'" % logfile_log_level)
        return False

    # Create and set formatter, add log file handler to logger
    logfile_formatter = LogFormatter(fmt=log_line_template, color=logfile_log_color)
    logfile_handler.setFormatter(logfile_formatter)
    logger.addHandler(logfile_handler)

    # Success
    return True

mac_pattern = re.compile("\taddress: [0-9a-f:]+")


ADU_DEFAULT_IP = '192.168.30.187'

STEP_NONE = 0
STEP_INSTALLATION = 1
STEP_FLASH = 2
STEP_REBOOT = 3
STEP_VERIFICATION = 4
STEP_DONE = 5
STEP_FAIL = -1
STEP_FAILURE_NOTIFIED = -2

def clear_ssh_host(ip = ADU_DEFAULT_IP):
    subprocess.call(
        ['ssh-keygen', '-f', '/home/plusai/.ssh/known_hosts', '-R', ip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def ssh_exec_command(ip: str, password :str, command: str) -> Tuple[int, str]:
    logging.info(f'on {ip} executing {command}')
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.MissingHostKeyPolicy())
    client.connect(ip, username='root', password=password, look_for_keys=False, allow_agent=False)
    stdin, stdout, stderr = client.exec_command(command)
    error_code = stdout.channel.recv_exit_status()
    output = stdout.readlines()
    err_out = stderr.readlines()
    del stdin, stdout, stderr
    client.close()

    return error_code, output

def try_passwords(ip: str):
    passwords = os.environ.get("ADU_ROOT_PASSWORDS").split(" ")
    for password in passwords:
        try:
            ec, output = ssh_exec_command(ip, password, 'echo hello')
            if (ec == 0):
                return password
        except:
            time.sleep(1)
    logging.error("SSH 密码都不好用")
    return None

# return True if the ip responds the ping
def ping(ip: str, repeat=3) -> bool:
    for i in range(repeat):
        child = subprocess.Popen(
            ['ping', ip, '-c', '1'], stdout=subprocess.PIPE)
        child.communicate()
        if child.returncode == 0:
            return True
    return False


class ADU(object):
    def __init__(self):
        self.ip = ADU_DEFAULT_IP
        self.mac = 'INVALID' # mac address of eq0
        self.id = 0
        self.plus_version = ''
        self.pdk_version = ''
        self.sn = 'N/A'
        self.password = ''
        self.bootchain = ''
        # step is the one to be performed
        self.step = STEP_INSTALLATION
        self.flash_process = None # the long running flash client process

    def pull_mac(self):
        ec, output = ssh_exec_command(self.ip, self.password, "ifconfig eq0 | grep address")
        if ec != 0:
            return ""
        if len(output) == 0:
            return ""
        mac = output[0]
        if (mac_pattern.match(mac)):
            self.mac = mac[10:-1].strip()
        logging.info(f'ADU MAC 地址 {self.mac}')
        return self.mac

    # flash_state.txt contains 1 when the ADU is in 2nd flashing phase
    def pull_flash_state(self):
        ec, output = ssh_exec_command(
            self.ip, self.password, "cat /data/doip_uds_flash/flash_state.txt")
        if ec != 0:
            logging.error(f"无法获取刷写标志位: {output}")
            return '0'
        if len(output) == 0:
            return '0'
        return output[0].strip()

    def pull_plus_plus_version(self):
        ec, output = ssh_exec_command(
            self.ip, self.password, "cat /usr/libnvidia/version-plus.txt")
        if ec != 0 or len(output) == 0 or len(output[0].strip()) == 0:
            logging.error(f"无法获取BSP版本")
            self.plus_version = "N/A"
        else:
            self.plus_version = output[0].strip()
        logging.warning(f"ADU 版本号 {self.plus_version}")
        return self.plus_version

    def pull_pdk_version(self):
        ec, output = ssh_exec_command(
            self.ip, self.password, "cat /usr/libnvidia/version-pdk.txt")
        if ec != 0 or len(output) == 0 or len(output[0].strip()) == 0:
            logging.error(f"无法获取PDK版本")
            self.pdk_version = "N/A"
        else:
            self.pdk_version = output[0].strip()[0:7]
        logging.warning(f"ADU PDK 版本号 {self.pdk_version}")
        return self.pdk_version

    def pull_bootchain(self):
        self.bootchain='N/A'
        try:
            ec, output = ssh_exec_command(self.ip, self.password, "/samples/driveupdate/sample_driveupdate -q 2>&1 ")
            if ec != 0 or len(output) == 0:
                pass
            else:
                for line in output:
                    if line.startswith("Tegra A"):
                        self.bootchain = line.split(':')[1].strip()
                logging.warning(f"ADU启动分区是 {self.bootchain}")
        except:
            pass
        return self.bootchain


    # based on the plus_version and flash_state
    def query_step(self, new_image_plus_version):
        plus_version = self.pull_plus_plus_version()
        if plus_version != new_image_plus_version:
            self.step = STEP_INSTALLATION
        else:
            flash_state = self.pull_flash_state()
            if flash_state == '0':
                self.step = STEP_DONE
            elif flash_state == '1':
                self.step = STEP_VERIFICATION
            else:
                self.step = STEP_FAIL

    def send_file(self, source_path: str, target_path: str):
        try:
            logging.info(f'ADU{self.id}@{self.ip} sending {source_path} to {target_path}')
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.MissingHostKeyPolicy())
            client.connect(self.ip, username='root', password=self.password)
            scp = SCPClient(client.get_transport())
            scp.put(source_path, target_path)
            client.close()
            return True
        except Exception as e:
            logging.error(e)
            return False

    def get_file(self, source_path: str, target_path: str):
        try:
            logging.info(f'ADU{self.id}@{self.ip} getting {source_path} to {target_path}')
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.MissingHostKeyPolicy())
            client.connect(self.ip, username='root', password=self.password)
            scp = SCPClient(client.get_transport())
            scp.get(source_path, target_path)
            client.close()
        except Exception as e:
            logging.error(e)

    def install_sn_and_flag_files(self):
        ec, output = ssh_exec_command(self.ip, self.password, f'printf "default\n" > /data/VIN && print "SN" > /data/SN &&printf "all_sensors: false\nublox: false\nside_radar: false\n" > /data/UNCHECKED')
        if ec != 0:
            logging.error(f"fail to install flag files on {self.id}@{self.ip} {output}")
            self.step = STEP_FAIL
            return False
        else:
            logging.warning(f"installed flag files on {self.id}@{self.ip} {self.sn}")
            return True

    def install_uds_server(self):
        logging.warning(f"在ADU上安装刷新服务器")
        ec, output = ssh_exec_command(
            self.ip, self.password, 'mkdir -p /home/plusai')
        if ec != 0:
            logging.error(f"fail to create /home/plusai on {self.id}@{self.ip} {output}")
            self.step = STEP_FAIL
            return False
        try:
            self.send_file('install_uds_server.sh', '/home/plusai')
            self.send_file('uds_server_package.tar.xz', '/home/plusai')
            ec, output = ssh_exec_command(
               self.ip, self.password, 'sh /home/plusai/install_uds_server.sh')
            if ec != 0:
               logging.error(f"fail to install uds server on {self.id}@{self.ip} {output}")
               self.step = STEP_FAIL
               return False
            key_path = os.environ.get('IMAGE_KEY_PATH')
            if not key_path or not os.path.exists(key_path):
                logging.error("Cannot find image key file")
            self.send_file(key_path, '/data/doip_uds_flash')
            logging.warning(f"安装成功")
            self.step = STEP_FLASH
            return True
        except Exception as e:
            logging.error(e)
            self.step = STEP_FAIL

    def flash_async(self):
        logging.warning(f"在ADU上部署离线刷写脚本")
        try:
            self.send_file('flash_async.sh', '/home/plusai')
            ec, output = ssh_exec_command(
               self.ip, self.password, 'nohup sh /home/plusai/flash_async.sh 2>/dev/null 1>/dev/null &')
            if ec != 0:
               logging.error(f"无法在ADU上执行离线刷写")
               self.step = STEP_FAIL
               return False
            return True
        except Exception as e:
            logging.error(e)
            self.step = STEP_FAIL
            return False

    def clean_up(self):
        ec, output = ssh_exec_command(
            self.ip, self.password, 'rm /home/plusai/install_uds_server.sh && rm /home/plusai/uds_server_package.tar.xz')

    def create_log_dir(self):
        self.log_dir = f'{os.getcwd()}/log/{self.id}'
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

    def flash(self):
        client = os.environ.get("UDS_CLIENT_PATH")
        # wait for doip uds start to init
        time.sleep(60)
        logging.warning(f"flashing {self.id}@{self.ip}")
        child = subprocess.Popen([client,
                                f'-host={self.ip}', 
                                f'-local_path={os.environ.get("IMAGE_PATH")}',
                                f'-tasks=plus_version:create_file:cksum:flash',
                                f'-checksum={os.environ.get("IMAGE_CHECKSUM")}'], stdout=subprocess.PIPE, stderr = subprocess.PIPE)

        self.step = STEP_FLASH
        self.flash_process = child

    def send_flash_image(self):
        client = os.environ.get("UDS_CLIENT_PATH")
        # wait for doip uds start to init
        time.sleep(60)
        logging.warning(f"flashing {self.id}@{self.ip}")
        child = subprocess.Popen([client,
                                f'-host={self.ip}', 
                                f'-local_path={os.environ.get("IMAGE_PATH")}',
                                f'-tasks=plus_version:create_file:cksum',
                                f'-checksum={os.environ.get("IMAGE_CHECKSUM")}'], stdout=subprocess.PIPE, stderr = subprocess.PIPE)

        self.step = STEP_FLASH
        self.flash_process = child

    def reset_ecu(self):
        client = os.environ.get("UDS_CLIENT_PATH")
        child = subprocess.run([client,
                                f'-host={self.ip}', 
                                f'-tasks=reset',
                                f'-checksum={os.environ.get("IMAGE_CHECKSUM")}'], stdout=subprocess.PIPE)
        if child.returncode != 0:
            logging.error(f'ADU {self.id}@{self.ip} fails to reset_ecu')
            self.step = STEP_FAIL
        else:
            logging.error(f'ADU {self.id}@{self.ip} is rebooting')
            self.step = STEP_VERIFICATION

def get_package_pdk_version():
    if not os.path.exists('version-pdk.txt'):
        logging.warning("找不到./version-pdk.txt, 默认版本5.2.3")
        return "5.2.3.0"
    with open('version-pdk.txt', 'r') as f:
        version = f.readlines()[0][0:7]
        logging.warning(f"刷机包 PDK 版本 {version}")
        return version

def prepare_uds_server_package(adu_pdk_version, image_pdk_version):
    package_name = f"uds_server_package_{adu_pdk_version}_{image_pdk_version}.tar.xz"
    if not os.path.exists(package_name):
        logging.error("没有找到所需刷机工具")
        exit(1)
    shutil.copy(package_name, 'uds_server_package.tar.xz')
    shutil.copy(f'install_uds_server_{adu_pdk_version}.sh', 'install_uds_server.sh')
    
def show_progress_bar(seconds):
    with alive_bar(seconds*10) as bar:
        for _ in range(seconds*10):
            time.sleep(0.1)
            bar()

def flash_handler():
    logging.warning("[连接ADU]->安装刷机软件->刷写备用启动分区->切换到新的启动分区")
    if not ping(ADU_DEFAULT_IP, 10):
        logging.error(f"ADU {ADU_DEFAULT_IP} ping 不通")
        exit(1)
    password = try_passwords(ADU_DEFAULT_IP)
    if not password:
        logging.error(f"ssh密码错误 {ADU_DEFAULT_IP}，请更新刷机工具")
        exit(1)
    adu = ADU()
    adu.ip = ADU_DEFAULT_IP
    adu.password = password
    adu.pull_pdk_version()
    image_pdk_version = get_package_pdk_version()
    prepare_uds_server_package(adu.pdk_version, image_pdk_version)
    adu.pull_mac()
    adu.create_log_dir()
    logging.warning("连接ADU->[安装刷机软件]->刷写备用启动分区->切换到新的启动分区")
    #adu.install_sn_and_flag_files()
    if not adu.install_uds_server():
        logging.error("安装刷机服务器失败, 请联系晨笛团队，可以优先联系魏文彬（如果他还在职）")
        exit(1)
    for i in range(6):
        logging.info('查询ADU启动分区(A/B)')
        chain_before = adu.pull_bootchain()
        if chain_before == 'A' or chain_before == 'B':
            break
        else:
            logging.warning("暂时无法获取启动分区，等待10秒重试")
            show_progress_bar(10)

    if chain_before != 'A' and chain_before != 'B':
        logging.error("无法获取当前启动分区，请重启车辆再试一次，还是不行的话请联系晨笛团队，可以优先联系魏文彬（如果他还在职）")
        exit(1)

    logging.warning("连接ADU->安装刷机软件->[刷写备用启动分区]->切换到新的启动分区")
    if len(sys.argv) == 2 and sys.argv[1] == 'async':
        logging.warning("离线刷写模式(开发中)")
        adu.send_flash_image()
        seconds = 600
        with alive_bar(seconds) as bar:
            for i in range(seconds):
                bar()
                poll = adu.flash_process.poll()
                if poll is None:
                    time.sleep(1)
                elif poll == 0:
                    if i < seconds - 1:
                        for _ in range(i + 1, seconds):
                            bar()
                    if adu.flash_async():
                        logging.warning("15分钟之后回来查看")
                        exit(0)
                    else:
                        logging.error("刷写失败")
                        exit(1)
                    break
                else:
                    logging.error("刷写失败")
                    for line in adu.flash_process.stdout.readlines():
                        print(line)
                    for line in adu.flash_process.stderr.readlines():
                        print(line)
                    exit(1)
    else:
        logging.warning("预计耗时20分钟，可以去干点儿别的")
        adu.flash()
        with alive_bar(1300) as bar:

            for i in range(1300):
                bar()
                poll = adu.flash_process.poll()
                if poll is None:
                    time.sleep(1)
                elif poll == 0:
                    if i < 1300 - 2:
                        for _ in range(i, 1300):
                            bar()
                    logging.warning(f"刷写完毕，ADU 将会自动重启两次")
                    break
                else:
                    logging.error("刷写失败")
                    for line in adu.flash_process.stdout.readlines():
                        print(line)
                    for line in adu.flash_process.stderr.readlines():
                        print(line)
                    exit(1)
    logging.warning("连接ADU->安装刷机软件->刷写备用启动分区->[切换到新的启动分区]")
    time.sleep(5)
    adu.reset_ecu()
    logging.warning("ADU即将重启，等待5分钟")
    show_progress_bar(300)
    if not ping(ADU_DEFAULT_IP, 10):
        logging.warning("ADU未能完成自动重启，请重启车辆, 登录ADU 确认刷新状态, cat /usr/libnvidia/plus_version-plus.txt， 如果看到是新版本，刷机成功，否则请联系晨笛团队，可以优先联系魏文彬（如果他还在职）")
        exit(1)
    logging.warning("检测ADU状态")
    adu.password = try_passwords(ADU_DEFAULT_IP)
    if not password:
        logging.error(f"ssh密码错误 {ADU_DEFAULT_IP}，请更新刷机工具")
        exit(1)
    chain_after = 'N/A'
    logging.info('确认ADU从新的分区启动...')
    for i in range(5):
        chain_after = adu.pull_bootchain()
        if chain_after == 'A' or chain_after == 'B':
            break
        else:
            logging.warning("暂时无法获取启动分区，等待30秒重试...")
            show_progress_bar(30)
    if chain_after != 'A' and chain_after != 'B':
        logging.error("ADU未能完成自动重启，请重启车辆, 登录ADU 确认刷新状态, cat /usr/libnvidia/plus_version-plus.txt， 如果看到是新版本，刷机成功，否则请联系晨笛团队，可以优先联系魏文彬（如果他还在职）")
        exit(1)
    if chain_after != chain_before:
        logging.warning("刷写成功")
        exit(0)
    logging.error("刷新失败， 还没遇到这种情况，请保留目录下日志文件，联系晨笛团队，可以优先联系魏文彬（如果他还在职）")
    exit(1)

def main():
    if (not setup_logging(console_log_output="stdout", console_log_level="info", console_log_color=True,
                        logfile_file=f"doip_flash_{datetime.now().isoformat()}.log", logfile_log_level="info", logfile_log_color=False,
                        log_line_template="%(color_on)s[%(asctime)s] [%(levelname)-8s] %(message)s%(color_off)s")):
        print("Failed to setup logging, aborting.")
        return 1
    flash_handler()

if __name__ == '__main__':
    main()
