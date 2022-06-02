'''
Author: zhao.gong
Date: 2022-06-02 11:23:55
LastEditTime: 2022-06-02 15:39:09
LastEditors: zhao.gong
Description: This file is designed as a back-end script for flashing ADU in an automatic manner.
FilePath: /diagnosis/flash/flash_warp.py
for problems, pls mail me zhao.gong@plus.ai
'''

import os
import subprocess
import argparse
import re
from threading import Timer
from utils import limit_decor
# from scp import SCPClient
from parallel_flash_529.main import exec_command

filePattern = "(.*?).tar.xz" #for ensuring the current file is selected.

def kill_process(p):
    p.kill()

def parse():
    parse = argparse.ArgumentParser(description="default")
    parse.add_argument("--input")
    parse.add_argument("--ip", default="192.168.11.100")
    return parse.parse_args()

def prepare(args) -> bool:
    file_name = args.input
    if len(re.findall(filePattern, file_name)) < 1:
        print("You have chosen a wrong file!")
    
    try:
        if(os.system("cp {} ./xavier_doip_flash_internal/dec-flash-images.tar.xz".format(args.input))
        + os.system("./xavier_doip_flash_internal/prepare_image.sh"))>1:
            raise Exception("FILE ISSUE")
        else:
            return True
    except:
        print("Preparation failed, please check the file you have selected!")
        return False

@limit_decor(1) #1s
def ping(ip: str, repeat=3) -> bool:
    for i in range(repeat):
        child = subprocess.Popen(
            ['ping', ip, '-c', '1'], stdout=subprocess.PIPE)
        child.communicate()
        if child.returncode == 0:
            return True
    return False

def inputCheck() -> bool:
    s = input("Shall we start testing the connection?[yes/no]")
    if s in ["yes", "Y", "YES", "Yes"]:
        return True
    else:
        return False

def connectionCheck(args) -> bool:
    flag = False
    while not flag:
        flag = inputCheck() and ping(args.ip)
        print("Connect testing failed, please check the connection between the computer and the ADU")
    return flag

def adu_bsp_confirm(args):
    ec, output = exec_command(
        args.ip, "cat /usr/libnvidia/version-plus.txt")
    if ec != 0 or len(output) == 0:
        version = "N/A"
    else:
        version = output[0].strip()
    return version

def flash():
    os.system("cd ./xavier_doip_flash_internal && ./flash.sh")
    
def main():
    args = parse()
    # prepare(args)
    # connectionCheck(args)   
    # adu_bsp_confirm(args)
    # flash()
    
    

if __name__ == "__main__":
    main()
