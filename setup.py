from distutils.core import setup

setup(name='freenav',
      version='0.0.1',
      description='FreeNav task and navigation programs',
      author='Alan Sparrow',
      scripts=['scripts/taskedit'],
      packages=['freenav'],
      package_dir={'freenav': 'src/freenav'},
      data_files=[('/usr/share/applications/hildon', ['data/taskedit.desktop']),
                  ('/usr/share/dbus-1/services', ['data/taskedit.service'])
                 ]
     )
