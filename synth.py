#!/usr/bin/env python3

# DEMO for University of Nottingham Science Fair (18-20th April 2018)
#   (Educational use.)
#
# Adapted from Pianoputer by Zulko (see below for CC licensing etc.):
#   http://zulko.github.io/blog/2014/03/29/soundstretching-and-pitch-shifting-in-python/
#   https://github.com/Zulko/pianoputer
#
# Requires GrovePi sensor board, ultrasonic sensor, PIR sensor, 
#   2 x light sensors, 3 LEDs
#

from scipy.io import wavfile
import argparse
import numpy as np
import pygame
import warnings

import threading
import time
import random
import grovepi#, grove6axis as g6a
import os, sys

MELODY     = pygame.USEREVENT + 1
DRONE_ON   = pygame.USEREVENT + 3
DRONE_OFF  = pygame.USEREVENT + 4
KICK       = pygame.USEREVENT + 5
SNARE      = pygame.USEREVENT + 6

# Ultrasound max and min calibration values
US_MAX = 60
US_MIN = 1

CALIB_STEPS = 4



def calibldr(pin, lmin, lmax):
    ls = []
    delta = 0
    for i in range(0, CALIB_STEPS):
        level = grovepi.analogRead(pin)
        if level < lmax:
            ls.append(level)
        else:
            i = i - 1
        time.sleep(0.2)
    lmax = sum(ls) / len(ls)
    return (lmax, ((lmax - lmin)/2))



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

    def __init__(self, pin, ledpin, res=0.1):
        threading.Thread.__init__(self)
        self.pin = pin
        self.ledpin = ledpin
    
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
                print("DRONE triggered        [filtered value (>=0.4): ",pvalf,"]")
                grovepi.digitalWrite(self.ledpin, 1)
            elif self.pval == 1 and pval == 0 and pvalf < 0.4:
                pygame.event.post(pygame.event.Event(DRONE_OFF))
                self.pval = pval
                print("DRONE off              [filtered value (<0.4): ",pvalf,"]")
                grovepi.digitalWrite(self.ledpin, 0)
            time.sleep(self.res)

class drumcontrol(threading.Thread):
    kill = 0
    l1val = 0
    l2val = 0
    kmax = 1000
    smax = 1000
    sd = 500
    kd = 500

    def __init__(self, ldrpins, ledpins, res=0.1):
        threading.Thread.__init__(self)
        self.ledpins = ledpins
        self.ldrpins = ldrpins
    
    def setcalib(self, kmax, kd, smax, sd):
        self.kmax = kmax
        self.kd = kd
        self.smax = smax
        self.sd = sd

    def setres(self, res):
        self.res = res

    def kill(self):
        self.kill = 1
    
    def run(self):
        while self.kill != 1:
            
            # LDR kick and snare
            l1val_ = grovepi.analogRead(self.ldrpins[0])
            l2val_ = grovepi.analogRead(self.ldrpins[1])

            #print ("l1val = ", l1val_, " l2val = ", l2val_)
            if l1val_ < self.kmax and l1val_ > self.l1val:
                self.l1val = l1val_
            elif self.l1val - l1val_ > self.kd:
                pygame.event.post(pygame.event.Event(KICK))
                #grovepi.digitalWrite(self.ledpins[0], 1)
                print("KICK triggered by LDR       [value: ",
                        l1val_, "; delta: ", self.l1val-l1val_, "]")
                self.l1val = l1val_

            if l2val_ < self.smax and l2val_ > self.l2val:
                self.l2val = l2val_
            elif self.l2val - l2val_ > self.sd:
                pygame.event.post(pygame.event.Event(SNARE))
                grovepi.digitalWrite(self.ledpins[1], 1)
                print("SNARE triggered by LDR       [value: ",
                        l2val_, "; delta: ", self.l2val-l2val_, "]")
                self.l2val = l2val_

            time.sleep(self.res)

            for pin in self.ledpins:
                grovepi.digitalWrite(pin, 0)


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
            
            '''
            g = g6a.getAccel()
            mag = sum(g) / len(g)
            
            '''
            
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

    # Headless
    #os.putenv('SDL_VIDEODRIVER', 'fbcon')
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    pygame.display.init()
    screen = pygame.display.set_mode((500, 400))

    fps, sound = wavfile.read(args.wavmldy.name)
    pygame.mixer.pre_init(fps, -16, 1, 2048)
    pygame.init()
    print(pygame.mixer.get_init())
    # Load drone sound, and drums
    drone = pygame.mixer.Sound(args.wavdrone.name)
    kick = pygame.mixer.Sound(args.wavkick.name)
    snare = pygame.mixer.Sound(args.wavsnare.name)
    kick.set_volume(1)
    snare.set_volume(1)
    drone.set_volume(0.1)

    
    tones = range(-int(np.floor(args.notes/2)), int(np.ceil(args.notes/2)))
    sys.stdout.write('Transposing sound file... ')
    sys.stdout.flush()
    transposed_sounds = [pitchshift(sound, n) for n in tones]
    print('DONE')

    keys = args.keyboard.read().split('\n')
    sounds = map(pygame.sndarray.make_sound, transposed_sounds)
    key_sound = dict(zip(keys, sounds))
    is_playing = {k: False for k in keys}



    mldythread = threads['mldythread']
    dronethread = threads['dronethread']
    drumthread = threads['drumthread']


    # Light calibration
    (kmax, kd) = calibldr(KICK_LDR_PIN, 1, 750)
    print("lmax, delta = ", kmax, kd)

    (smax, sd) = calibldr(SNARE_LDR_PIN, 1, 750)
    print("lmax, delta = ", smax, sd)


    mldythread.setres(0.1)
    mldythread.setnotes(args.notes)
    mldythread.start()
    
    dronethread.setres(0.3)
    dronethread.start()
    
    drumthread.setres(0.3)
    drumthread.setcalib(kmax, kd, smax, sd)
    drumthread.start()

    keyVal = None

    while mldythread.isAlive():

        event = pygame.event.wait()
        
        if event.type in (pygame.KEYDOWN, pygame.KEYUP):
            keyVal = pygame.key.name(event.key)
        elif event.type == MELODY:
            keyVal = event.message

        if event.type == MELODY:
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
        



MELODY_ULTRASONIC_PIN   = 2 #D2
KICK_LDR_PIN            = 0 #A0
KICK_LED_PIN            = 8 #D8
SNARE_LDR_PIN           = 1 #A1
SNARE_LED_PIN           = 7 #D7
DRONE_PIR_PIN           = 4 #D4
DRONE_LED_PIN           = 3 #D3

if __name__ == '__main__':

    grovepi.digitalWrite(KICK_LED_PIN, 0)
    grovepi.digitalWrite(SNARE_LED_PIN, 0)

    mldythread = mldycontrol(MELODY_ULTRASONIC_PIN)
    dronethread = dronecontrol(DRONE_PIR_PIN, DRONE_LED_PIN)
    drumthread = drumcontrol(ldrpins=(KICK_LDR_PIN, SNARE_LDR_PIN),
                             ledpins=(KICK_LED_PIN, SNARE_LED_PIN))

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

