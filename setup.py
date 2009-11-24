from distutils.core import setup

setup(name='freenav',
      version='0.0.1',
      description='FreeNav task and navigation programs',
      author='Alan Sparrow',
      scripts=['src/scripts/taskedit', 'src/scripts/freenav'],
      packages=['freenav'],
      package_dir={'freenav': 'src/freenav'},
      data_files=[('share/applications/hildon', ['data/taskedit.desktop']),
                  ('share/applications/hildon', ['data/freenav.desktop']),
                  ('share/dbus-1/services', ['data/taskedit.service'],
                  ('share/dbus-1/services', ['data/freenav.service'])
                 ]
     )
