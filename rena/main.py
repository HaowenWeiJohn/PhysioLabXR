import sys

from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt
# Press the green button in the gutter to run the script.
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtWidgets import QLabel, QSystemTrayIcon, QMenu

from MainWindow import MainWindow
from rena.startup import load_settings

# import and init shared global variables

app = None

if __name__ == '__main__':
    # load default settings
    load_settings(revert_to_default=False)

    # load the qt application
    app = QtWidgets.QApplication(sys.argv)
    tray_icon = QSystemTrayIcon(QIcon('icon.PNG'), parent=app)
    tray_icon.setToolTip('RNApp')
    tray_icon.show()

    # splash screen
    splash = QLabel()
    pixmap = QPixmap('../media/logo/RN.png')
    splash.setPixmap(pixmap)
    splash.setWindowFlags(Qt.SplashScreen | Qt.FramelessWindowHint)
    splash.show()

    # main window init
    # inference_interface = InferenceInterface.InferenceInterface()
    window = MainWindow(app=app)

    window.setWindowIcon(QIcon('../media/logo/RN.png'))
    # make tray menu
    menu = QMenu()
    exit_action = menu.addAction('Exit')
    exit_action.triggered.connect(window.close)

    # splash screen destroy
    splash.destroy()
    window.show()

    try:
        app.exec_()
        print('App closed by user')
        sys.exit()
    except KeyboardInterrupt:
        print('App terminate by KeybaordInterrupt')
        sys.exit()
