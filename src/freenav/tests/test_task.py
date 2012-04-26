import math
import nose.tools

import freenav.task

class TestClass:
    def setup(self):
        tp_list = [{'id': "TP1", 'x': 0, 'y': 0,
                    'radius1': 5000, 'angle1': 180, 'radius2': 0,
                    'angle12': 90, 'tp_type': 'TURNPOINT'},
                   {'id': "TP2", 'x': 50000, 'y': 0,
                    'radius1': 10000, 'angle1': 90,
                    'radius2': 500, 'angle2': 360,
                    'angle12': 315, 'tp_type': 'TURNPOINT'},
                   {'id': "TP3", 'x': 50000, 'y': 50000, 'altitude': 0,
                    'radius1': 1000,
                    'angle12': 180, 'tp_type': 'LINE'}]

        polar = {'a': -0.002117, 'b': 0.08998, 'c': -1.56}

        settings = {'bugs': 1.0,
                    'ballast': 1.0,
                    'safety_height': 100.0}

        self.task = freenav.task.Task(tp_list, polar, settings)
        self.task.reset()

    def test_nav1(self):
        self.task.start(0, 0, 1000, 0)
        self.task.task_position(0, 0, 1000, 0)
        nav = self.task.get_nav()

        nose.tools.assert_almost_equal(nav['distance'], 50000)
        nose.tools.assert_almost_equal(nav['bearing'], math.radians(90))

        self.task.next_turnpoint(0, 0, 1000, 0)
        nav = self.task.get_nav()

        nose.tools.assert_almost_equal(nav['distance'], 50000 * math.sqrt(2))
        nose.tools.assert_almost_equal(nav['bearing'], math.radians(45))

    def test_glide1(self):
        # No wind glide
        self.task.start(0, 0, 1000, 0)
        self.task.task_position(0, 0, 1000, 0)
        self.task.next_turnpoint(0, 0, 1000, 0)

        self.task.set_maccready(0)
        glide = self.task.get_glide()
        ld = 50000 * math.sqrt(2) / (1000 - glide['height'])
        nose.tools.assert_almost_equal(ld, 38.3, 1)

        self.task.set_maccready(2)
        glide = self.task.get_glide()
        ld = 50000 * math.sqrt(2) / (1000 - glide['height'])
        nose.tools.assert_almost_equal(ld, 38.3, 1)

    def test_glide2(self):
        # Glide with wind
        self.task.set_wind({'speed': 10, 'direction': math.pi / 4})

        self.task.start(0, 0, 1000, 0)
        self.task.task_position(0, 0, 1000, 0)
        self.task.next_turnpoint(0, 0, 1000, 0)

        self.task.set_maccready(0)
        glide = self.task.get_glide()
        ld = 50000 * math.sqrt(2) / (1000 - glide['height'])
        nose.tools.assert_almost_equal(ld, 38.3, 1)
