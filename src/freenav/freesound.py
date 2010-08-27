"""This module encapsulates sound handling for the freenav program"""

import fnmatch
import logging
import os
import os.path

import pygame.mixer

class Sound():
    """Sound encapsulation class"""
    def __init__(self):
        """Initialise pygame sounds"""
        self.logger = logging.getLogger('freelog')
        self.sounds = {}

        pygame.mixer.init()

        dir_path = os.path.join(os.getenv('HOME'), '.freeflight', 'sounds')
        for file in os.listdir(dir_path):
            if fnmatch.fnmatch(file, "*.wav"):
                sound = file.split(".")[0]
                wav_path = os.path.join(dir_path, file)
                try:
                    self.sounds[sound] = pygame.mixer.Sound(wav_path)
                except pygame.error:
                    self.logger.warning("Error loading sound %s" % sound)

    def play(self, sound):
        """Play the sound"""
        try:
            self.sounds[sound].play()
        except KeyError:
            pass

