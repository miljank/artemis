#!/usr/bin/env python3

import os
import sys
import time
import json
import wiringpi2
import threading
from   textstar import *

class Display(TextStar):
    def __init__(self, port, artemis, baud=9600, debug=False):
        self.active      = False
        self.artemis     = artemis
        self.key_handler = {}
        super(Display, self).__init__(port, baud=baud, debug=debug)

    def show(self, message):
        for index in range(len(message)):
            self.setCurPos(index + 1)
            self.sendCmd(message[index])

    def register_keys(self, keys=None):
        self.active      = False
        self.key_handler = {}
        if not isinstance(keys, dict):
            return False

        self.key_handler = keys

    def get_key(self):
        while artemis.wait_for_key:
            time.sleep(.1)
            key = self.getKey()

            if not key:
                if self.active is not False:
                    return self.active()
                continue

            if not self.active:
                if key in self.key_handler:
                    self.active = self.key_handler[key]
                    return self.active()
            else:
                self.active = False

class Artemis(object):
    def __init__(self, shutter_pin, motor_pin, frames=5, interval=2, shutter_index=2, time_to_end=160):
        self.motor_pin   = motor_pin
        self.shutter_pin = shutter_pin
        self.frame       = 1

        self.shutter_values = ['1/10', '1/8', '1/6', '1/5', '1/4', '0"3', '0"4', '0"5', '0"6',
                               '0"8', 1, '1"3', '1"6', 2, '2"5', 3, '3"2', 4, 5, 6, 7, 8, 10,
                               13, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60]

        self.frames        = frames
        self.interval      = interval
        self.time_to_end   = time_to_end
        self.settle_time   = 0.1
        self.shutter_index = shutter_index
        self.shutter_speed = self.get_shutter_speed(self.shutter_index)

        self.gpio        = wiringpi2.GPIO(wiringpi2.GPIO.WPI_MODE_PINS)
        self.screen      = [self.main_screen]
        self.display     = Display('/dev/ttyAMA0', artemis=self)
        self.config_file = os.path.expanduser("~/.artemisrc")

        self.load_config()
        self.setup_pins()
        self.calculate_intervals()

        self.run           = True
        self.wait_for_key  = True
        self.run_timelapse = True

    #######################################################
    # Support and config methods
    #######################################################
    def get_shutter_speed(self, position):
        speed = self.shutter_values[position]
        if isinstance(speed, str):
            if '/' in speed:
                speed = speed.split('/')
                return float(speed[0]) / float(speed[1])
            elif '"' in speed:
                return float(speed.replace('"', '.'))
        return speed

    def load_config(self):
        if os.path.isfile(self.config_file):
            config = {}
            try:
                with open(self.config_file) as f:
                    config = json.load(f)
            except ValueError:
                return False

            if "frames" in config:
                self.frames = config["frames"]
            if "interval" in config:
                self.interval = config["interval"]
            if "shutter" in config:
                self.shutter_index = config["shutter"]
                self.shutter_speed = self.get_shutter_speed(self.shutter_index)

    def save_config(self):
        config = {"frames": self.frames, "interval": self.interval, "shutter": self.shutter_index}
        json.dump(config, open(self.config_file, "w"))

    def calculate_intervals(self):
        self.motor_pulse   = self.time_to_end / float(self.frames)
        self.shutter_speed = self.get_shutter_speed(self.shutter_index)

        if self.motor_pulse > (self.interval - self.shutter_speed - self.settle_time):
            self.motor_pulse = self.interval - self.shutter_speed - self.settle_time

        self.sleep_time = self.interval - self.motor_pulse - self.shutter_speed

    def check_settings(self):
        if self.sleep_time < 0 or \
           self.motor_pulse > self.interval or \
           (self.motor_pulse + self.sleep_time) > self.interval:
            return False
        return True

    def setup_pins(self):
        self.gpio.pinMode(self.shutter_pin, self.gpio.OUTPUT)
        wiringpi2.pinMode(self.shutter_pin, 1)

        self.gpio.pinMode(self.motor_pin, self.gpio.OUTPUT)
        wiringpi2.pinMode(self.motor_pin, 1)

    #######################################################
    # Main screen
    #######################################################
    def set_main_screen(self):
        self.save_config()
        self.calculate_intervals()
        self.screen = [self.main_screen]
        return True

    def main_screen(self):
        message = ["< Timelapse    O",
                   "T:{:<2} F:{:<3} S:{:<3}".format(self.interval, self.frames,
                                                    self.shutter_values[self.shutter_index])]
        self.display.show(message)
        self.display.register_keys({"A": self.set_edit_interval_screen,
                                    "C": self.set_shoot_timelapse})
        self.display.get_key()

        return True

    #######################################################
    # Interval screen
    #######################################################
    def set_edit_interval_screen(self):
        self.screen = [self.edit_interval]

    def set_shoot_timelapse(self):
        self.screen = [self.shoot_timelapse, self.stop_timelapse]

    def interval_screen(self):
        message = ["< Interval     +",
                   "T: {:<4}        -".format(self.interval)]
        self.display.show(message)

    def edit_interval(self):
        self.interval_screen()
        self.display.register_keys({"A": self.set_edit_frames_screen,
                                    "C": self.increase_interval,
                                    "D": self.decrease_interval})

        while True:
            if self.display.get_key():
                return True

            self.interval_screen()

    def increase_interval(self):
        if self.interval != 30:
            self.interval += 1

    def decrease_interval(self):
        if self.interval > 1:
            self.interval -= 1

    #######################################################
    # Frames screen
    #######################################################
    def set_edit_frames_screen(self):
        self.save_config()
        self.screen = [self.edit_frames]
        return True

    def frames_screen(self):
        message = ["< Frames       +",
                   "F: {:<4}        -".format(self.frames)]
        self.display.show(message)

    def edit_frames(self):
        self.frames_screen()
        self.display.register_keys({"A": self.set_edit_speed_screen,
                                    "C": self.increase_frames,
                                    "D": self.decrease_frames})

        while True:
            if self.display.get_key():
                return True

            self.frames_screen()

    def increase_frames(self):
        self.frames += 1

    def decrease_frames(self):
        if self.frames != 1:
            self.frames -= 1

    #######################################################
    # Shutter speed screen
    #######################################################
    def set_edit_speed_screen(self):
        self.save_config()
        self.screen = [self.edit_speed]
        return True

    def speed_screen(self):
        message = ["< Shutter      +",
                   "S: {:<3}         -".format(self.shutter_values[self.shutter_index])]
        self.display.show(message)

    def edit_speed(self):
        self.speed_screen()
        self.display.register_keys({"A": self.set_main_screen,
                                    "C": self.increase_speed,
                                    "D": self.decrease_speed})

        while True:
            if self.display.get_key():
                return True
            self.speed_screen()

    def increase_speed(self):
        if self.shutter_index < (len(self.shutter_values) - 1):
            self.shutter_index += 1

    def decrease_speed(self):
        if self.shutter_index > 0:
            self.shutter_index -= 1

    #######################################################
    # Time-lapse screen
    #######################################################
    def timelapse_screen(self):
        message = [" Timelapse     X",
                   "{:>5}/{:<5}".format(self.frame, self.frames)]
        self.display.show(message)

    def delayed_start(self, pause=5):
        while pause > 0:
            self.display.show([" Starting in: {}".format(pause)])
            time.sleep(1)
            pause -= 1
        return True

    def shoot_timelapse(self):
        if not self.check_settings():
            self.run_timelapse = False
            self.screen = [self.main_screen]
            return False

        self.delayed_start()

        self.frame         = 1
        self.run_timelapse = True

        self.timelapse_screen()
        time.sleep(.5)

        while self.run_timelapse:
            self.timelapse_screen()
            self.take_photo()

            self.frame += 1
            if self.frame > self.frames:
                self.run_timelapse = False
                self.wait_for_key  = False
                break

            if self.frame == 1:
                time.sleep(self.motor_pulse)
                continue

            self.move_camera()
            time.sleep(self.sleep_time)

        self.screen = [self.main_screen]
        return True

    def stop_timelapse(self):
        self.display.register_keys({"C": self.set_stop_timelapse})

        while self.run_timelapse:
            if self.display.get_key():
                break
        self.wait_for_key = True
        return True

    def set_stop_timelapse(self):
        self.run_timelapse = False
        return True

    def take_photo(self):
        self.gpio.digitalWrite(self.shutter_pin, self.gpio.HIGH)
        time.sleep(self.shutter_speed)
        self.gpio.digitalWrite(self.shutter_pin, self.gpio.LOW)

    def move_camera(self):
        self.gpio.digitalWrite(self.motor_pin, self.gpio.HIGH)
        time.sleep(self.motor_pulse)
        self.gpio.digitalWrite(self.motor_pin, self.gpio.LOW)
        time.sleep(self.settle_time)

    #######################################################
    # Start the thing
    #######################################################
    def start_threads(self, threads=[]):
        pool = []
        for thread in threads:
            t = threading.Thread(target=thread)
            t.daemon = True
            t.start()
            pool.append(t)

        while pool:
            for thread in pool:
                thread.join()
                pool.remove(thread)
                break

    def main(self):
        while self.run:
            try:
                self.start_threads(self.screen)
            except KeyboardInterrupt:
                self.run           = False
                self.run_timelapse = False
                sys.exit()

if __name__ == '__main__':
    artemis = Artemis(shutter_pin=3, motor_pin=7)
    artemis.main()
