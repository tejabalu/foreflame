#!/bin/bash
#echo ‘Run this sh every minute’ >> /home/tejabalu/TerraVibes/data/test.log
source ~/anaconda3/bin/activate weather_env
cd /home/tejabalu/TerraVibes/data
python3 NOAA_gfs_data_prediction.py