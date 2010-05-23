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
            self.sounds[s] = pygame.mixer.Sound(os.path.join(dir, snd_file))

    def play(self, sound):
        self.sounds[sound].play()
