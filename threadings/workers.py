import time

import cv2
import pyqtgraph as pg
from PyQt5.QtCore import QObject
from PyQt5.QtCore import pyqtSignal
from pylsl import local_clock

import config_ui
from interfaces.InferenceInterface import InferenceInterface
from interfaces.LSLInletInterface import LSLInletInterface
from utils.sim import sim_openBCI_eeg, sim_unityLSL, sim_inference

import pyautogui

import numpy as np

from utils.ui_utils import dialog_popup
from datetime import datetime
import pylsl
from PyQt5.QtCore import (QCoreApplication, QObject, QRunnable, QThread,
                          QThreadPool, pyqtSignal, pyqtSlot)
from utils.data_utils import RNStream

class EEGWorker(QObject):
    """

    """
    # for passing data to the gesture tab
    signal_data = pyqtSignal(dict)
    tick_signal = pyqtSignal()

    def __init__(self, eeg_interface=None, *args, **kwargs):
        super(EEGWorker, self).__init__()
        self.tick_signal.connect(self.eeg_process_on_tick)
        if not eeg_interface:
            print('None type eeg_interface, starting in simulation mode')

        self._eeg_interface = eeg_interface
        self._is_streaming = False

        self.start_time = time.time()
        self.end_time = time.time()

    @pg.QtCore.pyqtSlot()
    def eeg_process_on_tick(self):
        if self._is_streaming:
            if self._eeg_interface:
                data = self._eeg_interface.process_frames()  # get all data and remove it from internal buffer
            else:  # this is in simulation mode
                # assume we only working with OpenBCI eeg
                data = sim_openBCI_eeg()

            # notify the eeg data for the radar tab
            data_dict = {'data': data}
            self.signal_data.emit(data_dict)

    def start_stream(self):
        if self._eeg_interface:  # if the sensor interfaces is established
            self._eeg_interface.start_sensor()
        else:
            print('EEGWorker: Start Simulating EEG data')
        self._is_streaming = True
        self.start_time = time.time()

    def stop_stream(self):
        if self._eeg_interface:
            self._eeg_interface.stop_sensor()
        else:
            print('EEGWorker: Stop Simulating eeg data')
            print('EEGWorker: frame rate calculation is not enabled in simulation mode')
        self._is_streaming = False
        self.end_time = time.time()

    def is_streaming(self):
        return self._is_streaming


class UnityLSLWorker(QObject):
    """

    """
    # for passing data to the gesture tab
    signal_data = pyqtSignal(dict)
    tick_signal = pyqtSignal()

    def __init__(self, unityLSL_interface=None, *args, **kwargs):
        super(UnityLSLWorker, self).__init__()
        self.tick_signal.connect(self.unityLSL_process_on_tick)
        if not unityLSL_interface:
            print('None type unityLSL_interface, starting in simulation mode')

        self._unityLSL_interface = unityLSL_interface
        self.is_streaming = False

        self.start_time = time.time()
        self.end_time = time.time()

    @pg.QtCore.pyqtSlot()
    def unityLSL_process_on_tick(self):
        if self.is_streaming:
            if self._unityLSL_interface:
                data, _ = self._unityLSL_interface.process_frames()  # get all data and remove it from internal buffer
            else:  # this is in simulation mode
                data = sim_unityLSL()

            data_dict = {'data': data}
            self.signal_data.emit(data_dict)

    def start_stream(self):
        if self._unityLSL_interface:  # if the sensor interfaces is established
            self._unityLSL_interface.start_sensor()
        else:
            print('UnityLSLWorker: Start Simulating Unity LSL data')
        self.is_streaming = True
        self.start_time = time.time()

    def stop_stream(self):
        if self._unityLSL_interface:
            self._unityLSL_interface.stop_sensor()
        else:
            print('UnityLSLWorker: Stop Simulating Unity LSL data')
            print('UnityLSLWorker: frame rate calculation is not enabled in simulation mode')
        self.is_streaming = False
        self.end_time = time.time()


class InferenceWorker(QObject):
    """

    """
    # for passing data to the gesture tab
    # signal_inference_results = pyqtSignal(np.ndarray)
    signal_inference_results = pyqtSignal(list)
    tick_signal = pyqtSignal(dict)

    def __init__(self, inference_interface: InferenceInterface=None, *args, **kwargs):
        super(InferenceWorker, self).__init__()
        self.tick_signal.connect(self.inference_process_on_tick)
        if not inference_interface:
            print('None type unityLSL_interface, starting in simulation mode')

        self.inference_interface = inference_interface
        self._is_streaming = True
        self.is_connected = False

        self.start_time = time.time()
        self.end_time = time.time()

    def connect(self):
        if self.inference_interface:
            self.inference_interface.connect_inference_result_stream()
            self.is_connected = True

    def disconnect(self):
        if self.inference_interface:
            self.inference_interface.disconnect_inference_result_stream()
            self.is_connected = False

    def inference_process_on_tick(self, samples_dict):
        if self._is_streaming:
            if self.inference_interface:
                inference_results = self.inference_interface.send_samples_receive_inference(samples_dict)  # get all data and remove it from internal buffer
            else:  # this is in simulation mode
                inference_results = sim_inference()  # TODO implement simulation mode
            if len(inference_results) > 0:
                self.signal_inference_results.emit(inference_results)


class LSLInletWorker(QObject):

    # for passing data to the gesture tab
    signal_data = pyqtSignal(dict)
    tick_signal = pyqtSignal()

    def __init__(self, LSLInlet_interface: LSLInletInterface, *args, **kwargs):
        super(LSLInletWorker, self).__init__()
        self.tick_signal.connect(self.process_on_tick)

        self._lslInlet_interface = LSLInlet_interface
        self.is_streaming = False

        self.start_time = time.time()
        self.num_samples = 0

    @pg.QtCore.pyqtSlot()
    def process_on_tick(self):
        if self.is_streaming:
            frames, timestamps= self._lslInlet_interface.process_frames()  # get all data and remove it from internal buffer

            self.num_samples += len(timestamps)
            try:
                sampling_rate = self.num_samples / (time.time() - self.start_time) if self.num_samples > 0 else 0
            except ZeroDivisionError:
                sampling_rate = 0
            data_dict = {'lsl_data_type': self._lslInlet_interface.lsl_data_type, 'frames': frames, 'timestamps': timestamps, 'sampling_rate': sampling_rate}
            self.signal_data.emit(data_dict)

    def start_stream(self):
        try:
            self._lslInlet_interface.start_sensor()
        except AttributeError as e:
            dialog_popup(e)
            return
        self.is_streaming = True

        self.num_samples = 0
        self.start_time = time.time()

    def stop_stream(self):
        self._lslInlet_interface.stop_sensor()
        self.is_streaming = False

class WebcamWorker(QObject):
    tick_signal = pyqtSignal()
    change_pixmap_signal = pyqtSignal(tuple)

    def __init__(self, cam_id):
        super().__init__()
        self.cap = None
        self.cam_id = cam_id
        self.cap = cv2.VideoCapture(int(self.cam_id))
        self.tick_signal.connect(self.process_on_tick)

    def release_webcam(self):
        if self.cap is not None:
            self.cap.release()

    @pg.QtCore.pyqtSlot()
    def process_on_tick(self):
        ret, cv_img = self.cap.read()
        if ret:
            cv_img = cv_img.astype(np.uint8)
            cv_img = cv2.resize(cv_img, (config_ui.cam_display_width, config_ui.cam_display_height), interpolation=cv2.INTER_NEAREST)
            self.change_pixmap_signal.emit((self.cam_id, cv_img, local_clock()))  # uses lsl local clock for syncing

class ScreenCaptureWorker(QObject):
    tick_signal = pyqtSignal()  # note that the screen capture follows visualization refresh rate
    change_pixmap_signal = pyqtSignal(tuple)

    def __init__(self, screen_label):
        super().__init__()
        self.tick_signal.connect(self.process_on_tick)
        self.screen_label = screen_label

    @pg.QtCore.pyqtSlot()
    def process_on_tick(self):
        img = pyautogui.screenshot()
        frame = np.array(img)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = frame.astype(np.uint8)
        frame = cv2.resize(frame, (config_ui.cam_display_width, config_ui.cam_display_height), interpolation=cv2.INTER_NEAREST)
        self.change_pixmap_signal.emit((self.screen_label, frame, local_clock()))  # uses lsl local clock for syncing


class DeviceWorker(QObject):
    """

    """
    # for passing data to the gesture tab
    signal_data = pyqtSignal(dict)
    tick_signal = pyqtSignal()

    def __init__(self, eeg_interface=None, *args, **kwargs):
        super(DeviceWorker, self).__init__()
        self.tick_signal.connect(self.eeg_process_on_tick)
        if not eeg_interface:
            print('None type eeg_interface, starting in simulation mode')

        self._eeg_interface = eeg_interface
        self.is_streaming = True

        self.start_time = time.time()
        self.end_time = time.time()

    @pg.QtCore.pyqtSlot()
    def eeg_process_on_tick(self):
        if self.is_streaming:
            if self._eeg_interface:
                data = self._eeg_interface.process_frames()  # get all data and remove it from internal buffer
            else:  # this is in simulation mode
                # assume we only working with OpenBCI eeg
                data = sim_openBCI_eeg()

            # notify the eeg data for the radar tab
            data_dict = {'data': data}
            self.signal_data.emit(data_dict)

    def start_stream(self):
        if self._eeg_interface:  # if the sensor interfaces is established
            self._eeg_interface.start_sensor()
        else:
            print('EEGWorker: Start Simulating EEG data')
        self.is_streaming = True
        self.start_time = time.time()

    def stop_stream(self):
        if self._eeg_interface:
            self._eeg_interface.stop_sensor()
        else:
            print('EEGWorker: Stop Simulating eeg data')
            print('EEGWorker: frame rate calculation is not enabled in simulation mode')
        self.is_streaming = False
        self.end_time = time.time()

    def is_streaming(self):
        return self.is_streaming

class LSLReplayWorker(QObject):
    tick_signal = pyqtSignal()
    def __init__(self):
        super(LSLReplayWorker, self).__init__()
        # rns_stream = RNStream('C:/Recordings/03_22_2021_16_43_45-Exp_realitynavigation-Sbj_0-Ssn_0 CLEANED.dats')
        self.stream_data = None#rns_stream.stream_in(ignore_stream=['0', 'monitor1'])
        self.tick_signal.connect(self.start_stream)
        self.stop_signal = False

    @pg.QtCore.pyqtSlot()
    def start_stream(self):
        # self.stream_data = stream_data
        stream_names = list(self.stream_data)

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
                stream_channel_count = self.stream_data[stream_name][0].shape[0]
                stream_channel_format = 'double64'
                stream_source_id = 'Replay Stream - ' + stream_name

                outletInfo = pylsl.StreamInfo(stream_name, '', stream_channel_count, 0.0, stream_channel_format,
                                              stream_source_id)

                outlets[streamIndex] = pylsl.StreamOutlet(outletInfo)
                print("\t" + str(streamIndex) + "\t" + stream_name)

        virtualTimeOffset = 0
        virtualTime = None

        for stream in stream_names:
            if virtualTime is None or self.stream_data[stream][1][0] < virtualTime:
                # determine when the recording started
                virtualTime = self.stream_data[stream][1][0]

        virtualTimeOffset = pylsl.local_clock() - virtualTime
        print("Offsetting replayed timestamps by " + str(virtualTimeOffset))

        print(datetime.now())
        # replay the recording
        while len(selectedStreamIndices) > 0:  # streams get removed from the list if there are no samples left to play

            nextStreamIndex = None
            nextBlockingTimestamp = None

            if self.stop_signal:
                break

            # determine which stream to send next
            for i, stream_name in enumerate(stream_names):
                stream = self.stream_data[stream_name]
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
            nextStream = self.stream_data[stream_names[nextStreamIndex]]
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
        # self.stop_replay_btn_pressed()
