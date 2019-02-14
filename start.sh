#!/bin/bash
export DISPLAY=:0.0

#python3 ./synth.py -n 10 -wm sine.wav -wd drone3.wav -wk kick.wav -ws snare.wav

cd /home/pi/uon-science-fair-demo/ && python3 ./synth.py -n 20 -wm c64-lead1.wav -wd minimoog-bass.wav -wk kick.wav -ws snare.wav
