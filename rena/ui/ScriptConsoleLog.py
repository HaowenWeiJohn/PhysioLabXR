import copy
from datetime import datetime

from PyQt5 import QtWidgets, uic
from PyQt5.QtCore import QMutex
from PyQt5.QtWidgets import QLabel, QHBoxLayout

from rena.config import CONSOLE_LOG_MAX_NUM_ROWS


class ScriptConsoleLog(QtWidgets.QWidget):

    def __init__(self):
        super().__init__()
        self.ui = uic.loadUi("ui/ScriptConsoleLog.ui", self)
        self.log_history = ''
        self.msg_labels = []
        self.ts_labels = []
        self.add_msg_mutex = QMutex()

        self.auto_scroll = False
        # One way to stop auto scrolling is by moving the mouse wheel.
        self.super_wheelEvent = copy.deepcopy(self.scrollArea.wheelEvent)
        self.scrollArea.wheelEvent = self.new_wheel_event
        # A second way to stop auto scrolling is by dragging the slider.
        self.scroll_bar = self.scrollArea.verticalScrollBar()
        self.scroll_bar.sliderMoved.connect(self.stop_auto_scroll)

        self.ClearLogBtn.clicked.connect(self.clear_log_btn_clicked)
        self.SaveLogBtn.clicked.connect(self.save_log_btn_clicked)
        self.scrollToBottomBtn.clicked.connect(self.scroll_to_bottom_btn_clicked)

    def new_wheel_event(self, e):
        self.stop_auto_scroll()
        self.super_wheelEvent(e)

    def print_msg(self, msg):
        self.add_msg_mutex.lock()
        msg_label = QLabel(msg)
        now = datetime.now()  # current date and time
        timestamp_string = now.strftime("[%m/%d/%Y, %H:%M:%S] ")
        timestamp_label = QLabel(timestamp_string)

        msg_label.adjustSize()
        timestamp_label.adjustSize()

        self.log_history += timestamp_string + msg + '\n'

        self.LogContentLayout.addRow(timestamp_label, msg_label)
        self.msg_labels.append(msg_label)
        self.ts_labels.append(timestamp_label)

        if len(self.msg_labels) > CONSOLE_LOG_MAX_NUM_ROWS:
            self.LogContentLayout.removeRow(self.msg_labels[0])
            self.msg_labels = self.msg_labels[1:]
            self.ts_labels = self.ts_labels[1:]

        self.add_msg_mutex.unlock()

        self.optionally_scroll_down()

    def clear_log_btn_clicked(self):
        self.add_msg_mutex.lock()
        for msg_label in self.msg_labels:
            self.LogContentLayout.removeRow(msg_label)
        self.msg_labels = []
        self.ts_labels = []
        self.add_msg_mutex.unlock()

    def save_log_btn_clicked(self):
        filename, _ = QtWidgets.QFileDialog.getSaveFileName()
        if filename:
            self.add_msg_mutex.lock()
            with open(filename, "w") as f:
                for msg_label, ts_label in zip(self.msg_labels, self.ts_labels):
                    f.write(ts_label.text() + msg_label.text() + '\n')
            self.add_msg_mutex.unlock()

    def scroll_to_bottom_btn_clicked(self):
        self.auto_scroll = True

    def stop_auto_scroll(self):
        self.auto_scroll = False

    def optionally_scroll_down(self):
        if self.auto_scroll:
            self.scroll_bar.setSliderPosition(self.scroll_bar.maximum())
