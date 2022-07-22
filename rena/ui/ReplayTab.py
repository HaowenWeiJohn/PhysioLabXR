# This Python file uses the following encoding: utf-8
import os
import pickle
import time
from multiprocessing import Process

from PyQt5 import QtCore
from PyQt5 import QtWidgets
from PyQt5 import QtWidgets, uic, sip

import numpy as np
from datetime import datetime

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QFileDialog

import rena.config
from rena import config, shared
from rena.sub_process.ReplayServer import start_replay_client
from rena.sub_process.TCPInterface import RenaTCPInterface
from rena.utils.data_utils import RNStream
from rena.utils.ui_utils import dialog_popup
import pylsl
from rena.threadings.workers import LSLReplayWorker
from PyQt5.QtCore import QObject, QThread, pyqtSignal
import pyqtgraph as pg
from rena.ui.ReplaySeekBar import ReplaySeekBar
from rena.ui.PlayBackWidget import PlayBackWidget
from rena.utils.ui_utils import AnotherWindow, another_window


class ReplayTab(QtWidgets.QWidget):
    playback_position_signal = pyqtSignal(int)
    play_pause_signal = pyqtSignal(bool)

    def __init__(self, parent):
        """
        :param lsl_data_buffer: dict, passed by reference. Do not modify, as modifying it makes a copy.
        :rtype: object
        """
        super().__init__()
        self.ui = uic.loadUi("ui/ReplayTab.ui", self)
        self.is_replaying = False

        self.StartReplayBtn.clicked.connect(self.start_replay_btn_pressed)
        self.StopReplayBtn.clicked.connect(self.stop_replay_btn_pressed)
        self.SelectDataDirBtn.clicked.connect(self.select_data_dir_btn_pressed)

        self.StartReplayBtn.setEnabled(False)
        self.StopReplayBtn.setEnabled(False)
        self.parent = parent

        self.file_loc = config.DEFAULT_DATA_DIR
        self.ReplayFileLoc.setText('')

        self.seekBar = None

        # Initialize replay worker
        self.lsl_replay_worker = LSLReplayWorker(
            self, self.playback_position_signal, self.play_pause_signal)
        # Move worker to thread
        self.lsl_replay_thread = pg.QtCore.QThread(self.parent)
        self.lsl_replay_thread.start()
        self.lsl_replay_worker.moveToThread(self.lsl_replay_thread)

        self.replay_timer = QTimer()
        self.replay_timer.setInterval(config.REFRESH_INTERVAL)
        self.replay_timer.timeout.connect(self.ticks)

        # start replay client
        self.command_info_interface = RenaTCPInterface(stream_name='RENA_REPLAY',
                                                       port_id=config.replay_port,
                                                       identity='client',
                                                       pattern='router-dealer')

        # self.replay_client_process = Process(target=start_replay_client)
        # self.replay_client_process.start()

    def _open_playback_widget(self):
        self._init_playback_widget()
        print("did this start? playback")
        # open in a separate window
        # window = AnotherWindow(self.playback_widget, self.stop_replay_btn_pressed)
        self.playback_window = another_window('Playback')
        self.playback_window.get_layout().addWidget(self.playback_widget)
        self.playback_window.setFixedWidth(620)
        self.playback_window.setFixedHeight(300)
        self.playback_window.show()
        self.playback_window.activateWindow()
        print("shown yet?")

    def _init_playback_widget(self):
        self.playback_widget = PlayBackWidget(self)
        self.playback_widget.playback_signal.connect(self.on_playback_slider_changed)
        self.playback_widget.play_pause_signal.connect(self.on_play_pause_toggle)
        self.playback_widget.stop_signal.connect(self.stop_replay_btn_pressed)

        # connect signal emitted from the replayworker to playback widget
        self.lsl_replay_worker.replay_progress_signal.connect(self.playback_widget.on_replay_tick)

    def select_data_dir_btn_pressed(self):

        selected_data_dir = QFileDialog.getOpenFileName(self.widget_3, "Select File")[0]

        if selected_data_dir != '':
            self.file_loc = selected_data_dir

        # self.file_loc = self.file_loc + 'data.dats'

        print("Selected file: ", self.file_loc)
        self.ReplayFileLoc.setText(self.file_loc + '/')
        self.StartReplayBtn.setEnabled(True)

    def start_replay_btn_pressed(self):
        # if not (len(self.parent.LSL_data_buffer_dicts.keys()) >= 1 or len(self.parent.cam_workers) >= 1):
        #     dialog_popup('You need at least one LSL Stream or Capture opened to start recording!')
        #     return
        # self.save_path = self.generate_save_path()  # get a new save path

        # TODO: add progress bar
        self._open_playback_widget()
        print('Sending start command with file location to ReplayClient')  # TODO change the send to a progress bar
        self.command_info_interface.send_string(shared.START_COMMAND + self.file_loc)
        client_info = self.command_info_interface.recv_string()
        if client_info.startswith(shared.FAIL_INFO):
            dialog_popup(client_info.strip(shared.FAIL_INFO), title="ERROR")
        elif client_info.startswith(shared.SUCCESS_INFO):
            print('Received replay start success from ReplayClient')  # TODO change the send to a progress bar
        else:
            raise ValueError("ReplayTab.start_replay_btn_pressed: unsupported info from ReplayClient: " + client_info)
        # self.lsl_replay_worker.setup_stream()
        # self.replay_timer.start()

        # stream_names = list(stream_data)
        # self.parent.add_streams_from_replay(stream_names)
        # self.StartReplayBtn.setEnabled(False)
        # self.StopReplayBtn.setEnabled(True)
        # self.on_play_pause_toggle()  # because worker's is_playing status should be set to True as well

    def stop_replay_btn_pressed(self):
        self.is_replaying = False
        self.lsl_replay_worker.stop_signal = True
        self.parent.worker_threads['lsl_replay'].exit()
        self.StopReplayBtn.setEnabled(False)
        self.StartReplayBtn.setEnabled(True)

    def lsl_replay(self, stream_data):
        stream_names = list(stream_data)

        outlets = []
        nextSampleOfStream = []  # index of the next sample of each stream that will be send
        chunk_sizes = []  # how many samples should be published at once
        for i in range(0, len(stream_names)):
            outlets.append(None)
            nextSampleOfStream.append(0)
            chunk_sizes.append(1)

        print("Creating outlets")
        print("\t[index]\t[name]")

        def isStreamVideo(stream):
            if stream.isdigit():
                return True
            if ("monitor" in stream) or ("video" in stream):
                return True
            return False

        selectedStreamIndices = list(range(0, len(stream_names)))

        for streamIndex, stream_name in enumerate(stream_names):
            if not isStreamVideo(stream_name):
                stream_channel_count = stream_data[stream_name][0].shape[0]
                stream_channel_format = 'double64'
                stream_source_id = 'Replay Stream - ' + stream_name

                outletInfo = pylsl.StreamInfo(stream_name, '', stream_channel_count, 0.0, stream_channel_format,
                                              stream_source_id)

                outlets[streamIndex] = pylsl.StreamOutlet(outletInfo)
                print("\t" + str(streamIndex) + "\t" + stream_name)

        virtualTimeOffset = 0
        virtualTime = None

        for stream in stream_names:
            if virtualTime is None or stream_data[stream][1][0] < virtualTime:
                # determine when the recording started
                virtualTime = stream_data[stream][1][0]

        virtualTimeOffset = pylsl.local_clock() - virtualTime
        print("Offsetting replayed timestamps by " + str(virtualTimeOffset))

        print(datetime.now())
        # replay the recording
        while len(selectedStreamIndices) > 0:  # streams get removed from the list if there are no samples left to play

            nextStreamIndex = None
            nextBlockingTimestamp = None

            # determine which stream to send next
            for i, stream_name in enumerate(stream_names):
                stream = stream_data[stream_name]
                # when a chunk can be send depends on it's last sample's timestamp
                blockingElementIdx = nextSampleOfStream[i] + chunk_sizes[i] - 1
                try:
                    blockingTimestamp = stream[1][blockingElementIdx]
                except Exception as e:
                    print(e)
                if nextBlockingTimestamp is None or blockingTimestamp <= nextBlockingTimestamp:
                    nextStreamIndex = i
                    nextBlockingTimestamp = blockingTimestamp

            # retrieve the data and timestamps to be send
            nextStream = stream_data[stream_names[nextStreamIndex]]
            chunkSize = chunk_sizes[nextStreamIndex]

            nextChunkRangeStart = nextSampleOfStream[nextStreamIndex]
            nextChunkRangeEnd = nextChunkRangeStart + chunkSize

            nextChunkTimestamps = nextStream[1][nextChunkRangeStart: nextChunkRangeEnd]
            nextChunkValues = (nextStream[0][:, nextChunkRangeStart: nextChunkRangeEnd]).transpose()

            # prepare the data (if necessary)
            if isinstance(nextChunkValues, np.ndarray):
                # load_xdf loads numbers into numpy arrays (strings will be put into lists). however, LSL doesn't seem to
                # handle them properly as providing data in numpy arrays leads to falsified data being sent. therefore the data
                # are converted to lists
                nextChunkValues = nextChunkValues.tolist()
            nextSampleOfStream[nextStreamIndex] += chunkSize

            stream_length = nextStream[0].shape[-1]
            # calculates a lower chunk_size if there are not enough samples left for a "complete" chunk
            if stream_length < nextSampleOfStream[nextStreamIndex] + chunkSize:
                chunk_sizes[nextStreamIndex] = stream_length - nextSampleOfStream[nextStreamIndex]

            virtualTime = pylsl.local_clock() - virtualTimeOffset
            # TODO: fix this
            sleepDuration = nextBlockingTimestamp - virtualTime
            if sleepDuration > 0:
                time.sleep(sleepDuration)

            outlet = outlets[nextStreamIndex]
            nextStreamName = stream_names[nextStreamIndex]
            if chunkSize == 1:
                # print(str(nextChunkTimestamps[0] + virtualTimeOffset) + "\t" + nextStreamName + "\t" + str(nextChunkValues[0]))
                outlet.push_sample(nextChunkValues[0], nextChunkTimestamps[0] + virtualTimeOffset)
            else:
                # according to the documentation push_chunk can only be invoked with exactly one (the last) time stamp
                outlet.push_chunk(nextChunkValues, nextChunkTimestamps[-1] + virtualTimeOffset)
                # chunks are not printed to the terminal because they happen hundreds of times per second and therefore
                # would make the terminal output unreadable

            # remove this stream from the list if there are no remaining samples
            if nextSampleOfStream[nextStreamIndex] >= stream_length:
                selectedStreamIndices.remove(selectedStreamIndices[nextStreamIndex])
                outlets.remove(outlets[nextStreamIndex])
                nextSampleOfStream.remove(nextSampleOfStream[nextStreamIndex])
                chunk_sizes.remove(chunk_sizes[nextStreamIndex])
                stream_names.remove(stream_names[nextStreamIndex])

        print(datetime.now())
        self.stop_replay_btn_pressed()

    def openWindow(self):
        self.window = QtWidgets.QMainWindow()

    def ticks(self):
        self.lsl_replay_worker.replay()

    def on_play_pause_toggle(self):
        print("ReplayTab: toggle is replaying")
        self.is_replaying = not self.is_replaying
        self.play_pause_signal.emit(self.is_replaying)

    def on_playback_slider_changed(self, new_playback_position):
        print("adjust playback position to:", new_playback_position)
        self.playback_position_signal.emit(new_playback_position)
