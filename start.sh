#!/bin/bash

### PUT LINE BELOW vvvv IN rc.local 
#/bin/su pi -c "/usr/bin/screen -dmS synth bash -c '/home/pi/uon-science-fair-demo/start.sh; exec bash'"
### 

LOGFILE=/home/pi/uon-science-fair-demo/messages.log

echo Starting synth... [`date "+%F %T"`] >>$LOGFILE

export DISPLAY=:0

cd /home/pi/uon-science-fair-demo/

#python3 ./synth.py -n 10 -wm sine.wav -wd drone3.wav -wk kick.wav -ws snare.wav
python3 ./synth.py -n 20 -wm c64-lead1.wav -wd minimoog-bass.wav -wk kick.wav -ws snare.wav &

#xterm -display :0 -e "screen -r synth" &>>$LOGFILE
