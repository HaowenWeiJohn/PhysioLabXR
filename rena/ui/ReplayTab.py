# This Python file uses the following encoding: utf-8
import json
from multiprocessing import Process

import numpy as np
from PyQt6 import QtWidgets, uic
from PyQt6.QtCore import pyqtSignal, Qt, QSize
from PyQt6.QtGui import QMovie
from PyQt6.QtWidgets import QFileDialog, QDialogButtonBox, QWidget, QHBoxLayout, QLabel, QCheckBox, QListWidgetItem

from rena import config, shared
from rena.configs.configs import AppConfigs
from rena.presets.Presets import PresetType
from rena.sub_process.ReplayServer import start_replay_server
from rena.sub_process.TCPInterface import RenaTCPInterface
from rena.threadings.WaitThreads import start_wait_process, start_wait_for_response
from rena.ui.PlayBackWidget import PlayBackWidget
from rena.utils.lsl_utils import get_available_lsl_streams
from rena.utils.ui_utils import another_window
from rena.utils.ui_utils import dialog_popup

class ReplayStreamHeader(QWidget):
    def __init__(self):
        super().__init__()
        self.ui = uic.loadUi(AppConfigs()._ui_ReplayStreamHeaderWidget, self)

class ReplayStreamListItem(QWidget):
    def __init__(self, replay_tab_parent, stream_name, stream_shape, srate, enabled_in_replay=True, stream_interface=PresetType.LSL):
        """

        @param stream_name:
        @param stream_shape: channel x number of timepoints
        @param num_enabled_in_replay:
        """
        super().__init__()
        self.replay_tab_parent = replay_tab_parent
        self.ui = uic.loadUi(AppConfigs()._ui_ReplayStreamListItemWidget, self)
        self.stream_name = stream_name
        self.name_label.setText(f'{stream_name}')
        self.shape_label.setText(f'{stream_shape}')
        self.srate_label.setText(f'{srate:.3f} Hz')
        self.include_in_replay_checkbox.setChecked(enabled_in_replay)

        self.interface_combobox.addItem(PresetType.LSL.value)
        self.interface_combobox.addItem(PresetType.ZMQ.value)
        # select the current interface
        self.interface_combobox.setCurrentText(stream_interface.value)
        # add on change listener
        self.interface_combobox.currentTextChanged.connect(self.interface_combobox_changed)
        self.set_zmq_port_line_edit()

    def interface_combobox_changed(self):
        self.set_zmq_port_line_edit()
        self.replay_tab_parent.update_port_numbers()

    def set_zmq_port_line_edit(self):
        current_interface = self.interface_combobox.currentText()
        if current_interface == PresetType.LSL.value:
            self.zmq_port_line_edit.setVisible(False)
        else:
            self.zmq_port_line_edit.setVisible(True)

    def change_port(self, port):
        self.zmq_port_line_edit.setText(str(port))

    def is_enabled_in_replay(self):
        return self.include_in_replay_checkbox.isChecked()

    def get_info(self):
        return self.interface_combobox.currentText(), int(self.zmq_port_line_edit.text())

class ReplayTab(QtWidgets.QWidget):
    playback_position_signal = pyqtSignal(int)
    play_pause_signal = pyqtSignal(bool)

    def __init__(self, parent):
        """
        :param lsl_data_buffer: dict, passed by reference. Do not modify, as modifying it makes a copy.
        :rtype: object
        """
        super().__init__()
        self.ui = uic.loadUi(AppConfigs()._ui_ReplayTab, self)
        self.is_replaying = False  # note this attribute will still be true even when the replay is paused
        self.replay_speed = 1
        self.wait_worker = None
        self.wait_thread = None
        self.loading_replay_dialog = None
        self.loading_canceled = False
        self.start_time, self.end_time, self.total_time, self.virtual_clock_offset = None, None, None, None

        self.loading_label.setVisible(False)
        self.loading_movie = QMovie(AppConfigs()._icon_load_48px)
        self.loading_label.setMovie(self.loading_movie)

        self.stream_list_widget.setVisible(False)
        self.StartStopReplayBtn.clicked.connect(self.start_stop_replay_btn_pressed)
        self.StartStopReplayBtn.setVisible(False)

        self.SelectDataDirBtn.clicked.connect(self.select_data_dir_btn_pressed)

        self.parent = parent

        self.file_loc = config.DEFAULT_DATA_DIR
        self.ReplayFileLoc.setText('')
        self.stream_info = {}
        self.stream_list_items = {}

        # start replay client
        self.command_info_interface = RenaTCPInterface(stream_name='RENA_REPLAY',
                                                       port_id=config.replay_port,
                                                       identity='client',
                                                       pattern='router-dealer')
        self._create_playback_widget()

        self.replay_server_process = Process(target=start_replay_server)
        self.replay_server_process.start()

    def _create_playback_widget(self):
        self._init_playback_widget()
        # open in a separate window
        # window = AnotherWindow(self.playback_widget, self.stop_replay_btn_pressed)
        self.playback_window = another_window('Playback')
        self.playback_window.get_layout().addWidget(self.playback_widget)
        # self.playback_window.setFixedWidth(620)
        # self.playback_window.setFixedHeight(300)
        self.playback_window.hide()

    def _init_playback_widget(self):
        self.playback_widget = PlayBackWidget(self, self.command_info_interface)
        # self.playback_widget.playback_signal.connect(self.on_playback_slider_changed)
        # self.playback_widget.play_pause_signal.connect(self.on_play_pause_toggle)
        # self.playback_widget.stop_signal.connect(self.stop_replay_btn_pressed)

        # connect signal emitted from the replayworker to playback widget
        # self.lsl_replay_worker.replay_progress_signal.connect(self.playback_widget.on_replay_tick)

    def select_data_dir_btn_pressed(self):
        selected_file = QFileDialog.getOpenFileName(self.BottomWidget, "Select File")[0]
        self.select_file(selected_file)

    def select_file(self, selected_file):
        if selected_file != '':
            self.file_loc = selected_file

        # self.file_loc = self.file_loc + 'data.dats'

        print("Selected file: ", self.file_loc)
        self.ReplayFileLoc.setText(self.file_loc + '/')

        # start loading the replay file
        self.SelectDataDirBtn.setEnabled(False)
        self.show_loading()
        self.StartStopReplayBtn.setVisible(False)

        self.command_info_interface.send_string(shared.LOAD_COMMAND + self.file_loc)
        self.wait_worker, self.wait_thread = start_wait_for_response(socket=self.command_info_interface.socket)
        self.wait_worker.result_available.connect(self.process_reply_from_load_command)

    def process_reply_from_load_command(self):
        # if self.loading_canceled:  # TODO implement canceling loading of replay file
        #     self.StartStopReplayBtn.setEnabled(True)
        #     self.StartStopReplayBtn.setText('Start Replay')
        #     return
        # self.loading_replay_dialog.close()
        client_info = self.command_info_interface.recv_string()

        if client_info.startswith(shared.FAIL_INFO):
            dialog_popup(client_info.strip(shared.FAIL_INFO), title="ERROR")
            self.SelectDataDirBtn.setEnabled(True)
            self.hide_loading()
            self.stream_list_widget.setVisible(False)
        elif client_info.startswith(shared.LOAD_SUCCESS_INFO):
            time_info = self.command_info_interface.socket.recv()
            self.start_time, self.end_time, self.total_time, self.virtual_clock_offset = np.frombuffer(time_info)

            self.stream_info = {s_name: dict() for s_name in self.command_info_interface.recv_string().split('|')}

            # set the replay list
            self.stream_list_widget.setVisible(True)
            self.stream_list_widget.clear()

            # add header
            header_item = ReplayStreamHeader()
            item = QListWidgetItem()
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)  # Make the item non-selectable
            self.stream_list_widget.addItem(item)
            self.stream_list_widget.setItemWidget(item, header_item)
            self.stream_list_items = {}
            for s_name in self.stream_info.keys():
                n_channels, n_timepoints, srate = np.frombuffer(self.command_info_interface.socket.recv())
                n_channels, n_timepoints = int(n_channels), int(n_timepoints)
                self.stream_info[s_name]['n_channels'], self.stream_info[s_name]['n_timepoints'], self.stream_info[s_name]['srate'] = n_channels, n_timepoints, srate
                stream_list_item = ReplayStreamListItem(self, s_name, (n_channels, n_timepoints), srate)
                item = QListWidgetItem()
                item.setSizeHint(QSize(item.sizeHint().width(), 60))
                self.stream_list_widget.addItem(item)
                self.stream_list_widget.setItemWidget(item, stream_list_item)
                self.stream_list_items[s_name] = stream_list_item
            self.update_port_numbers()

            self.StartStopReplayBtn.setVisible(True)
            self.SelectDataDirBtn.setEnabled(True)
            self.stream_list_widget.setVisible(True)
            self.hide_loading()
        else:
            raise ValueError("ReplayTab.start_replay_btn_pressed: unsupported info from ReplayClient: " + client_info)

    def cancel_loading_replay(self):
        self.wait_worker.exit()
        self.command_info_interface.send_string(shared.CANCEL_START_REPLAY_COMMAND)
        self.loading_canceled = True

    def start_stop_replay_btn_pressed(self):
        """
        callback function when start_stop button is pressed.
        """
        print('Sending start command with file location to ReplayClient')

        if not self.is_replaying:
            existing_streams_before_replay = get_available_lsl_streams()
            try:
                if (overlapping_streams := set(existing_streams_before_replay).intersection(self.get_replay_lsl_stream_names())):  # if there are streams that are already streaming on LSL
                    reply = dialog_popup(
                        f'There\'s another stream source with the name {overlapping_streams} on the network.\n'
                        f'Are you sure you want to proceed with replaying this file? \n'
                        f'Proceeding may result in unpredictable streaming behavior.\n'
                        f'It is recommended to remove the other data stream with the same name.',
                        title='Duplicate Stream Name', mode='modal', main_parent=self.parent,
                        buttons=QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No)
                    if not reply.result(): raise AssertionError
                        # self.command_info_interface.send_string(shared.CANCEL_START_REPLAY_COMMAND)
                        # return
                self.stream_info = self.get_replay_stream_info()
            except AssertionError:
                self.StartStopReplayBtn.setEnabled(True)
                self.StartStopReplayBtn.setText('Start Replay')
                return
            self.playback_window.show()
            self.playback_window.activateWindow()
            self.playback_widget.start_replay(self.start_time, self.end_time, self.total_time, self.virtual_clock_offset)

            self.command_info_interface.send_string(shared.GO_AHEAD_COMMAND)
            self.command_info_interface.send_string(json.dumps(self.stream_info))
            # receive the new timing info
            self.start_time, self.end_time, self.total_time, self.virtual_clock_offset = np.frombuffer(self.command_info_interface.socket.recv())

            self.parent.add_streams_from_replay(list(self.stream_info.keys()))
            print('Received replay starts successfully from ReplayClient')  # TODO change the send to a progress bar
            self.is_replaying = True
            self.StartStopReplayBtn.setText('Stop Replay')
            self.StartStopReplayBtn.setEnabled(True)
            self.SelectDataDirBtn.setEnabled(False)
            # self.loading_canceled = False  # TODO implement canceling loading of replay file
            # self.loading_replay_dialog = dialog_popup('Loading replay file...', title='Starting Replay', mode='modeless', main_parent=self.parent, buttons=QDialogButtonBox.StandardButton.Cancel)
            # self.loading_replay_dialog.buttonBox.rejected.connect(self.cancel_loading_replay)
        else:
            self.stop_replay_btn_pressed()  # it is not known if the replay has successfully stopped yet
            self.playback_window.hide()
            self.replay_successfully_stopped()

    def stop_replay_btn_pressed(self):
        self.playback_widget.issue_stop_command()

    # def replay_successfully_paused(self):
        # self.StartStopReplayBtn.setText('Resume Replay')
        # self.is_replaying = False

    def replay_successfully_stopped(self):
        self.is_replaying = False
        self.SelectDataDirBtn.setEnabled(True)
        self.StartStopReplayBtn.setText('Start Replay')

    def openWindow(self):
        self.window = QtWidgets.QMainWindow()

    def try_close(self):
        self.playback_widget.issue_terminate_command()
        self.playback_widget.try_close()
        self.playback_window.close()  # opened windows must be closed
        self.replay_server_process.join(timeout=1)
        if self.replay_server_process.is_alive():
            self.replay_server_process.kill()
        return True

    # def ticks(self):
    #     self.lsl_replay_worker.tick_signal.emit()

    # def on_play_pause_toggle(self):
    #     self.is_replaying = not self.is_replaying
    #     self.play_pause_signal.emit(self.is_replaying)

    def on_playback_slider_changed(self, new_playback_position):
        print("adjust playback position to:", new_playback_position)
        self.playback_position_signal.emit(new_playback_position)

    def get_num_replay_channels(self):
        return len(self.stream_info)

    def _request_replay_performance(self):
        print('Sending performance request command ReplayClient')  # TODO change the send to a progress bar
        self.command_info_interface.send_string(shared.PERFORMANCE_REQUEST_COMMAND)
        average_loop_time = self.command_info_interface.socket.recv()  # this is blocking, but replay should respond fast
        average_loop_time = np.frombuffer(average_loop_time)[0]
        return average_loop_time

    def update_port_numbers(self):
        for i, (s_name, list_item) in enumerate(self.stream_list_items.items()):
            list_item.change_port(AppConfigs().replay_stream_starting_port + i)

    def get_replay_stream_info(self):
        rtn = {}
        zmq_ports = []
        for i, (s_name, list_item) in enumerate(self.stream_list_items.items()):
            if list_item.is_enabled_in_replay():
                rtn[s_name] = list_item.get_info()
                if rtn[s_name][0] == PresetType.ZMQ.value: zmq_ports.append(rtn[s_name][1])
        assert len(zmq_ports) == len(set(zmq_ports)), 'ZMQ ports cannot have duplicates'
        return rtn

    def show_loading(self):
        self.loading_label.show()
        self.loading_movie.start()

    def hide_loading(self):
        self.loading_label.hide()
        self.loading_movie.stop()

    def get_replay_lsl_stream_names(self):
        rtn = []
        for i, (s_name, list_item) in enumerate(self.stream_list_items.items()):
            if list_item.get_info()[0] == PresetType.LSL.value: rtn.append(s_name)
        return rtn