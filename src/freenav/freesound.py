import os.path

import pygame.mixer

SOUNDS = ['sector', 'line', 'ahead', 'right-front', 'right', 'right-back',
          'behind', 'left-back', 'left', 'left-front']

class Sound():
    def __init__(self):
        # Initialise pygame sounds
        pygame.mixer.init()
        dir = os.path.join(os.getenv('HOME'), '.freeflight', 'sounds')
        self.sounds = {}
        for s in SOUNDS:
            snd_file = s + '.wav'
            try:
                self.sounds[s] = pygame.mixer.Sound(os.path.join(dir, snd_file))
            except pygame.error:
                print "Error loading sound", s

    def play(self, sound):
        try:
            self.sounds[sound].play()
        except KeyError:
            pass

