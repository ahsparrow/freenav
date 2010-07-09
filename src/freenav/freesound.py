"""This module encapsulates sound handling for the freenav program"""

import logging
import os.path

import pygame.mixer

SOUNDS = ['sector', 'line', 'ahead', 'right-front', 'right', 'right-back',
          'behind', 'left-back', 'left', 'left-front']

class Sound():
    """Sound encapsulation class"""
    def __init__(self):
        """Initialise pygame sounds"""
        self.logger = logging.getLogger('freelog')

        pygame.mixer.init()
        dir_path = os.path.join(os.getenv('HOME'), '.freeflight', 'sounds')
        self.sounds = {}
        for sound in SOUNDS:
            snd_file = sound + '.wav'
            try:
                self.sounds[sound] = pygame.mixer.Sound(
                        os.path.join(dir_path, snd_file))
            except pygame.error:
                self.logger.warning("Error loading sound %s" % sound)

    def play(self, sound):
        """Play the sound"""
        try:
            self.sounds[sound].play()
        except KeyError:
            pass

