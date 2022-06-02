#!/bin/bash
rm -rf flash-images.tar.xz
rm -rf tmp
mkdir tmp
tar -zxvf dec-flash-images.tar.xz -C tmp
cp tmp/version-pdk.txt .
cp tmp/version-plus.txt .
rm -rf tmp
if [[ -f "version-pdk.txt" ]]; then
  openssl enc -e -aes-256-cbc -K `cat image_key` -iv 0 -in dec-flash-images.tar.xz -out flash-images.tar.xz
else
  openssl enc -e -aes-256-ecb -K `cat image_key` -in dec-flash-images.tar.xz -out flash-images.tar.xz
fi
