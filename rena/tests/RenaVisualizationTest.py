"""
If you have get file not found error, make sure you set the working directory to .../RealityNavigation/rena
Otherwise, you will get either import error or file not found error
"""

# reference https://www.youtube.com/watch?v=WjctCBjHvmA
import os
import random
import sys
import threading
import unittest
import uuid
from multiprocessing import Process

import pytest
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QMessageBox
from pytestqt.qtbot import QtBot

from rena.MainWindow import MainWindow
from rena.config import stream_availability_wait_time
from rena.startup import load_settings
from rena.tests.TestStream import LSLTestStream, ZMQTestStream
from rena.tests.test_utils import update_test_cwd, handle_custom_dialog_ok, handle_current_dialog_ok
from rena.utils.settings_utils import create_default_preset
from rena.utils.ui_utils import CustomDialog


@pytest.fixture
def app(qtbot: QtBot):
    print('Initializing test fixture for ' + 'Visualization Features')
    update_test_cwd()
    print(os.getcwd())
    # ignore the splash screen and tree icon
    app = QtWidgets.QApplication(sys.argv)
    # app initializationfix type error
    load_settings(revert_to_default=True, reload_presets=True)  # load the default settings
    test_renalabapp = MainWindow(app=app, ask_to_close=False)  # close without asking so we don't pend on human input at the end of each function test fixatire
    test_renalabapp.show()
    qtbot.addWidget(test_renalabapp)
    return test_renalabapp

def teardown_function(function):
    """ teardown any state that was previously setup with a setup_method
    call.
    """
    pass

def test_add_inactive_unknown_stream_in_added_stream_widgets(app, qtbot) -> None:
    '''
    Adding inactive stream
    :param app:
    :param qtbot:
    :return:
    '''
    test_stream_name = 'TestStreamName'

    app.ui.tabWidget.setCurrentWidget(app.ui.tabWidget.findChild(QWidget, 'visualization_tab'))  # switch to the visualization widget
    qtbot.mouseClick(app.addStreamWidget.stream_name_combo_box, QtCore.Qt.LeftButton)  # click the add widget combo box
    qtbot.keyPress(app.addStreamWidget.stream_name_combo_box, 'a', modifier=Qt.ControlModifier)
    qtbot.keyClicks(app.addStreamWidget.stream_name_combo_box, test_stream_name)
    qtbot.mouseClick(app.addStreamWidget.add_btn, QtCore.Qt.LeftButton)  # click the add widget combo box

    assert test_stream_name in app.get_added_stream_names()

def test_add_active_unknown_stream_in_added_stream_widgets(app, qtbot) -> None:
    '''
    Adding active stream
    :param app:
    :param qtbot:
    :return:
    '''
    test_stream_name = 'TestStreamName'
    p = Process(target=LSLTestStream, args=(test_stream_name,))
    p.start()

    app.ui.tabWidget.setCurrentWidget(app.ui.tabWidget.findChild(QWidget, 'visualization_tab'))  # switch to the visualization widget
    qtbot.mouseClick(app.addStreamWidget.stream_name_combo_box, QtCore.Qt.LeftButton)  # click the add widget combo box
    qtbot.keyPress(app.addStreamWidget.stream_name_combo_box, 'a', modifier=Qt.ControlModifier)
    qtbot.keyClicks(app.addStreamWidget.stream_name_combo_box, test_stream_name)
    qtbot.mouseClick(app.addStreamWidget.add_btn, QtCore.Qt.LeftButton)  # click the add widget combo box

    assert test_stream_name in app.get_added_stream_names()
    p.kill()  # stop the dummy LSL process
#
# def test_stream_availablity(app, qtbot):
#     pass

# def test_running_random_stream(app, qtbot):
#     pass
#     # TODO

# def test_label_after_click(app, qtbot):
#     qtbot.mouseClick(app.button, QtCore.Qt.LeftButton)
#     assert app.text_label.text() == "Changed!"

def test_lsl_channel_mistmatch(app, qtbot) -> None:
    '''
    Adding active stream
    :param app:
    :param qtbot:
    :return:
    '''
    test_stream_name = 'TestStreamName' + str(uuid.uuid4())
    actual_num_chan = random.randint(100, 200)
    preset_num_chan = random.randint(1, 99)
    streaming_time_second = 3

    p = Process(target=LSLTestStream, args=(test_stream_name, actual_num_chan))
    p.start()

    app.create_preset(test_stream_name, 'float', None, 'LSL', num_channels=preset_num_chan)  # add a default preset

    app.ui.tabWidget.setCurrentWidget(app.ui.tabWidget.findChild(QWidget, 'visualization_tab'))  # switch to the visualization widget
    qtbot.mouseClick(app.addStreamWidget.stream_name_combo_box, QtCore.Qt.LeftButton)  # click the add widget combo box
    qtbot.keyPress(app.addStreamWidget.stream_name_combo_box, 'a', modifier=Qt.ControlModifier)
    qtbot.keyClicks(app.addStreamWidget.stream_name_combo_box, test_stream_name)

    qtbot.mouseClick(app.addStreamWidget.add_btn, QtCore.Qt.LeftButton)  # click the add widget combo box
    qtbot.wait(int(stream_availability_wait_time * 1e3))
    def stream_is_available():
        assert app.stream_widgets[test_stream_name].is_stream_available
    qtbot.waitUntil(stream_is_available, timeout=int(2 * stream_availability_wait_time * 1e3))  # wait until the LSL stream becomes available

    # def handle_dialog():
    #     w = app.current_dialog
    #     if isinstance(w, CustomDialog):
    #         yes_button = w.button(QtWidgets.QMessageBox.Yes)
    #         qtbot.mouseClick(yes_button, QtCore.Qt.LeftButton, delay=1000)  # delay 1 second for the data to come in

    t = threading.Timer(1, lambda: handle_current_dialog_ok(app, qtbot, click_delay_second=1))   # get the messagebox about channel mismatch
    t.start()
    qtbot.mouseClick(app.stream_widgets[test_stream_name].StartStopStreamBtn, QtCore.Qt.LeftButton)
    t.join()

    qtbot.wait(int(streaming_time_second * 1e3))

    # check if data is being plotted
    assert app.stream_widgets[test_stream_name].viz_data_buffer.has_data()

    print("Test complete, killing sending-data process")
    p.kill()  # stop the dummy LSL process


def test_zmq_channel_mistmatch(app, qtbot) -> None:
    '''
    Adding active stream
    :param app:
    :param qtbot:
    :return:
    '''
    test_stream_name = 'TestStreamName' + str(uuid.uuid4())
    port = '5556'
    streaming_time_second = 3

    p = Process(target=ZMQTestStream, args=(test_stream_name, port))
    p.start()

    app.create_preset(test_stream_name, 'float', port, 'ZMQ', num_channels=random.randint(1, 99))  # add a default preset

    app.ui.tabWidget.setCurrentWidget(app.ui.tabWidget.findChild(QWidget, 'visualization_tab'))  # switch to the visualization widget
    qtbot.mouseClick(app.addStreamWidget.stream_name_combo_box, QtCore.Qt.LeftButton)  # click the add widget combo box
    qtbot.keyPress(app.addStreamWidget.stream_name_combo_box, 'a', modifier=Qt.ControlModifier)
    qtbot.keyClicks(app.addStreamWidget.stream_name_combo_box, test_stream_name)

    qtbot.mouseClick(app.addStreamWidget.add_btn, QtCore.Qt.LeftButton)  # click the add widget combo box
    qtbot.wait(int(stream_availability_wait_time * 1e3))

    def stream_is_available():
        assert app.stream_widgets[test_stream_name].is_stream_available
    qtbot.waitUntil(stream_is_available, timeout=int(2 * stream_availability_wait_time * 1e3))  # wait until the LSL stream becomes available

    # def handle_dialog():
    #     w = app.current_dialog
    #     if isinstance(w, CustomDialog):
    #         yes_button = w.button(QtWidgets.QMessageBox.Yes)
    #         qtbot.mouseClick(yes_button, QtCore.Qt.LeftButton, delay=1000)  # delay 1 second for the data to come in
    def waitForCurrentDialog():
        assert app.current_dialog
    t = threading.Timer(4, lambda: handle_current_dialog_ok(app, qtbot, click_delay_second=1))   # get the messagebox about channel mismatch
    t.start()
    qtbot.mouseClick(app.stream_widgets[test_stream_name].StartStopStreamBtn, QtCore.Qt.LeftButton)
    qtbot.waitUntil(waitForCurrentDialog)
    t.join()

    qtbot.wait(int(streaming_time_second * 1e3))

    # check if data is being plotted
    assert app.stream_widgets[test_stream_name].viz_data_buffer.has_data()

    print("Test complete, killing sending-data process")
    p.kill()  # stop sending data via ZMQ