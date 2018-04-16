#!/usr/bin/env python3

# DEMO for University of Nottingham Science Fair (18-20th April 2018)
#   (Educational use.)
#
# Adapted from Pianoputer by Zulko (see below for CC licensing etc.):
#   http://zulko.github.io/blog/2014/03/29/soundstretching-and-pitch-shifting-in-python/
#   https://github.com/Zulko/pianoputer
#
# Requires GrovePi sensor board, ultrasonic sensor, 3 x PIR sensors, 
#   2 x light sensors
#

from scipy.io import wavfile
import argparse
import numpy as np
import pygame
import sys
import warnings

import threading
import time
import random
import grovepi
import os

MELODY     = pygame.USEREVENT + 1
DRONE_ON   = pygame.USEREVENT + 3
DRONE_OFF  = pygame.USEREVENT + 4
KICK       = pygame.USEREVENT + 5
SNARE      = pygame.USEREVENT + 6

# Ultrasound max and min calibration values
US_MAX = 60
US_MIN = 1

# Light sensor max and min calibration values
L_MAX = 750
L_MIN = 70
L_DELTA = (L_MAX - L_MIN) / 2

def speedx(snd_array, factor):
    """ Speeds up / slows down a sound, by some factor. """
    indices = np.round(np.arange(0, len(snd_array), factor))
    indices = indices[indices < len(snd_array)].astype(int)
    return snd_array[indices]

def stretch(snd_array, factor, window_size, h):
    """ Stretches/shortens a sound, by some factor. """
    phase = np.zeros(window_size)
    hanning_window = np.hanning(window_size)
    result = np.zeros(int(len(snd_array) / factor + window_size))

    for i in np.arange(0, len(snd_array) - (window_size + h), h*factor):
        i = int(i)
        # Two potentially overlapping subarrays
        a1 = snd_array[i: i + window_size]
        a2 = snd_array[i + h: i + window_size + h]

        # The spectra of these arrays
        s1 = np.fft.fft(hanning_window * a1)
        s2 = np.fft.fft(hanning_window * a2)

        # Rephase all frequencies
        phase = (phase + np.angle(s2/s1)) % 2*np.pi

        a2_rephased = np.fft.ifft(np.abs(s2)*np.exp(1j*phase))
        i2 = int(i/factor)
        result[i2: i2 + window_size] += hanning_window*a2_rephased.real

    # normalize (16bit)
    result = ((2**(16-4)) * result/result.max())

    return result.astype('int16')

def pitchshift(snd_array, n, window_size=2**13, h=2**11):
    """ Changes the pitch of a sound by ``n`` semitones. """
    print("pitchshift,",n)
    factor = 2**(1.0 * n / 12.0)
    stretched = stretch(snd_array, 1.0/factor, window_size, h)
    return speedx(stretched[window_size:], factor)


def parse_arguments():
    description = ("RPI + GrovePi synth (adapted from pianoputer)")

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        '--wavmldy', '-wm',
        metavar='FILE',
        type=argparse.FileType('r'),
        default='sine.wav',
        help='WAV file (default: sine.wav)')
    parser.add_argument(
        '--wavdrone', '-wd',
        metavar='FILE',
        type=argparse.FileType('r'),
        default='drone.wav',
        help='MP3 file (default: drone.wav)')
    parser.add_argument(
        '--wavkick', '-wk',
        metavar='FILE',
        type=argparse.FileType('r'),
        default='kick.wav',
        help='MP3 file (default: kick.wav)')
    parser.add_argument(
        '--wavsnare', '-ws',
        metavar='FILE',
        type=argparse.FileType('r'),
        default='snare.wav',
        help='MP3 file (default: snare.wav)')
    parser.add_argument(
        '--keyboard', '-k',
        metavar='FILE',
        type=argparse.FileType('r'),
        default='list.kb',
        help='keyboard file (default: list.kb)')
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='verbose mode')
    parser.add_argument(
        '--notes', '-n',
        type=int,
        default=50,
        help='number of notes on keyboard')

    return (parser.parse_args(), parser)

'''
class lcontrol(threading.Thread):
    kill = 0
    lval = 1.0

    def __init__(self, pin=2, res=0.1):
        threading.Thread.__init__(self)
        self.pin = pin
        self.lval = L_MAX

    def setres(self, res):
        self.res = res

    def kill(self):
        self.kill = 1

    def run(self):
        while self.kill != 1:
            lval = grovepi.analogRead(self.pin)
            if lval > L_MAX:
                lval = L_MAX
            elif lval < L_MIN:
                lval = L_MIN
            
            lval_ = round((lval - L_MIN) / (L_MAX - L_MIN), 1)
            if lval_ != self.lval:
                print("scaled lval: ", lval_, " [raw: ", lval, "]")
                self.lval = lval_
                pygame.event.post(pygame.event.Event(LVAL, message=self.lval))
            time.sleep(self.res)
'''

class dronecontrol(threading.Thread):
    kill = 0
    pval = 0

    def __init__(self, pin=4, res=0.1):
        threading.Thread.__init__(self)
        self.pin = pin
    
    def setres(self, res):
        self.res = res

    def kill(self):
        self.kill = 1
    
    def run(self):
        const = 0.1
        pvalf = 0
        while self.kill != 1:
            pval = grovepi.digitalRead(self.pin)
            pvalf = pvalf * (1.0-const) + pval * const
            if self.pval == 0 and pval == 1:
                pygame.event.post(pygame.event.Event(DRONE_ON))
                self.pval = pval
                print("DRONE triggered      [filtered value (>=0.4): ",pvalf,"]")
            elif self.pval == 1 and pval == 0 and pvalf < 0.4:
                pygame.event.post(pygame.event.Event(DRONE_OFF))
                self.pval = pval
                print("DRONE off            [filtered value (<0.4): ",pvalf,"]")
            time.sleep(self.res)

class drumcontrol(threading.Thread):
    kill = 0
    l1val = L_MAX
    l2val = L_MAX

    def __init__(self, pirpins=(7, 8), ldrpins=(1, 2), res=0.1):
        threading.Thread.__init__(self)
        self.pirpins = pirpins
        self.ldrpins = ldrpins
    
    def setres(self, res):
        self.res = res

    def kill(self):
        self.kill = 1
    
    def run(self):
        p1val = [0, 0]
        p2val = [0, 0]
        qp1 = 0
        qp2 = 0
        while self.kill != 1:
            # PIR kick and snare
            p1val_ = grovepi.digitalRead(self.pirpins[0])
            p2val_ = grovepi.digitalRead(self.pirpins[1])
            
            # LDR kick and snare
            l1val_ = grovepi.analogRead(self.ldrpins[0])
            l2val_ = grovepi.analogRead(self.ldrpins[1])
            print ("l1val = ", l1val_, " l2val = ", l2val_)
            if l1val_ > self.l1val:
                self.l1val = l1val_
            elif self.l1val - l1val_ > L_DELTA:
                pygame.event.post(pygame.event.Event(KICK))
                print("KICK triggered by LDR       [value: ",l1val_,"]")
                self.l1val = l1val_

            if l2val_ > self.l2val:
                self.l2val = l2val_
            elif self.l2val - l2val_ > L_DELTA:
                pygame.event.post(pygame.event.Event(SNARE))
                print("SNARE triggered by LDR       [value: ",l2val_,"]")
                self.l2val = l2val_

            if p1val == [0, 0] and p1val_ == 1:
                pygame.event.post(pygame.event.Event(KICK))
                print("KICK triggered by PIR       [value: ",p1val_,"]")
            p1val[qp1] = p1val_
            qp1 = (qp1 + 1) % 2
            
            if p2val == [0, 0] and p2val_ == 1:
                pygame.event.post(pygame.event.Event(SNARE))
                print("SNARE triggered by PIR      [value: ",p2val_,"]")
            p2val[qp2] = p2val_
            qp2 = (qp2 + 1) % 2

            time.sleep(self.res)


class mldycontrol(threading.Thread):
    uval = 0
    kill = 0

    def __init__(self, pin=3, res=0.5, notes=10):
        threading.Thread.__init__(self)
        self.res = res
        self.notes = notes
        self.pin = pin

    def setres(self, res):
        self.res = res

    def setnotes(self, notes):
        self.notes = notes

    def getuval(self):
        return self.uval

    def run(self):
        while self.kill != 1:
            uval = grovepi.ultrasonicRead(self.pin)
            if uval < US_MAX and uval >= US_MIN:
                uval_ = int(((uval * (self.notes - 1)) / (US_MAX - US_MIN)) + 1)
                print("MELODY note: ",uval_, "      [raw value: ",uval,"]")
                if uval_ != self.uval:
                    self.uval = uval_
                    pygame.event.post(pygame.event.Event(MELODY, message=str(self.uval)))
            time.sleep(self.res)

    def kill(self):
        self.kill = 1



def main(threads):
    # Parse command line arguments
    (args, parser) = parse_arguments()

    # Enable warnings from scipy if requested
    if not args.verbose:
        warnings.simplefilter('ignore')


    fps, sound = wavfile.read(args.wavmldy.name)
    pygame.mixer.pre_init(fps, -16, 1, 2048)
    pygame.init()

    # Load drone sound, and drums
    drone = pygame.mixer.Sound(args.wavdrone.name)
    kick = pygame.mixer.Sound(args.wavkick.name)
    snare = pygame.mixer.Sound(args.wavsnare.name)
    kick.set_volume(0.4)
    snare.set_volume(0.4)
    drone.set_volume(0.3)

    tones = range(-int(np.floor(args.notes/2)), int(np.ceil(args.notes/2)))
    sys.stdout.write('Transposing sound file... ')
    sys.stdout.flush()
    transposed_sounds = [pitchshift(sound, n) for n in tones]
    print('DONE')

    keys = args.keyboard.read().split('\n')
    sounds = map(pygame.sndarray.make_sound, transposed_sounds)
    key_sound = dict(zip(keys, sounds))
    is_playing = {k: False for k in keys}

    # For the focus
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    screen = pygame.display.set_mode((150, 150))
#   os.putenv('SDL_VIDEODRIVER', 'fbcon')
#   pygame.display.init()

    mldythread = threads['mldythread']
    dronethread = threads['dronethread']
    drumthread = threads['drumthread']

    mldythread.setres(0.1)
    mldythread.setnotes(args.notes)
    mldythread.start()
    
    dronethread.setres(0.3)
    dronethread.start()
    
    drumthread.setres(0.3)
    drumthread.start()

    keyVal = None

    while mldythread.isAlive():

        event = pygame.event.wait()
        
        if event.type in (pygame.KEYDOWN, pygame.KEYUP):
            keyVal = pygame.key.name(event.key)
        elif event.type == MELODY:
            keyVal = event.message

        if event.type == MELODY:
            print("MELODY event ", keyVal)
            if (keyVal in key_sound.keys()) and (not is_playing[keyVal]):
                key_sound[keyVal].play(fade_ms=50)
                #is_playing[keyVal] = True
        '''        
        if event.type == MELODY_OFF and keyVal in key_sound.keys():
            print("Sensor turning off key value ", keyVal)
            # Stops with 50ms fadeout
            key_sound[keyVal].fadeout(50)
            is_playing[keyVal] = False
        '''
        
        if event.type == DRONE_ON:
            drone.play()
        elif event.type == DRONE_OFF:
            drone.fadeout(500)

        if event.type == KICK:
            kick.play()
        
        if event.type == SNARE:
            snare.play()
        '''            
        if event.type == VOLUME:
            volume = event.message
            drone.set_volume(lval)
            #map(lambda k: k.set_volume(lval), key_sound.values())
            for i in key_sound.values():
                i.set_volume(lval)
        '''

        # Pianoputer keyboard triggers
        if event.type == pygame.KEYDOWN:
            print("KEYDOWN")
            if (keyVal in key_sound.keys()) and (not is_playing[keyVal]):
                key_sound[keyVal].play(fade_ms=50)
                is_playing[keyVal] = True
                print("Keyboard playing key value ", keyVal)
            elif event.key == pygame.K_ESCAPE:
                pygame.quit()
                raise KeyboardInterrupt
        elif event.type == pygame.KEYUP and keyVal in key_sound.keys():
            print("KEYUP")
            # Stops with 50ms fadeout
            key_sound[keyVal].fadeout(50)
            is_playing[keyVal] = False
        


if __name__ == '__main__':

    mldythread = mldycontrol(2)
    dronethread = dronecontrol(3)
    drumthread = drumcontrol(pirpins=(7,8), ldrpins=(1,2))

    try:
        main({'mldythread' : mldythread, 
              'dronethread' : dronethread, 
              'drumthread' : drumthread})
    except (KeyboardInterrupt, SystemExit):
        print("Quitting...")
        mldythread.kill()
        dronethread.kill()
        drumthread.kill()
        sys.exit()

