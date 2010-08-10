from distutils.core import setup

setup(name='freenav',
      version='0.1.7',
      description='FreeNav task and navigation programs',
      author='Alan Sparrow',
      scripts=['src/scripts/taskedit', 'src/scripts/freenav',
               'src/scripts/freeconf', 'src/scripts/freexyz'],
      packages=['freenav'],
      package_dir={'freenav': 'src/freenav'},
      data_files=[('share/applications/hildon', ['data/taskedit.desktop',
                                                 'data/freenav.desktop',
                                                 'data/freeconf.desktop',
                                                 'data/freexyz.desktop']),
                  ('share/dbus-1/services', ['data/taskedit.service',
                                             'data/freenav.service',
                                             'data/freeconf.service',
                                             'data/freexyz.service']),
                  ('share/pixmaps', ['pixmaps/free_glider.png',
                                     'pixmaps/free_navarrow.png',
                                     'pixmaps/free_wind.png',
                                     'pixmaps/free_muted.png'])]
     )
