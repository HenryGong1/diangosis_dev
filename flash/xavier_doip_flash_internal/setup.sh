#!/bin/bash
sudo apt-get install python3-venv
python3 -m venv venv
source venv/bin/activate
python3 -m pip install --upgrade pip
pip3 install -r requirements.txt
