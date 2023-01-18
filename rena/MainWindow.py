import os
import random
import sys
import time
import webbrowser

import pyqtgraph as pg
from PyQt5 import QtWidgets, sip, uic
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtWidgets import QWidget

from exceptions.exceptions import RenaError
from rena import config
from rena.sub_process.TCPInterface import RenaTCPInterface
from rena.ui.AddWiget import AddStreamWidget
from rena.ui.ScriptingTab import ScriptingTab
from rena.ui.VideoDeviceWidget import VideoDeviceWidget
from rena.ui_shared import num_active_streams_label_text
from rena.utils.settings_utils import get_presets_by_category, get_childKeys_for_group, create_default_preset, \
    check_preset_exists, get_experiment_preset_streams

try:
    import rena.config
except ModuleNotFoundError as e:
    print('Make sure you set the working directory to ../RealityNavigation/rena, cwd is ' + os.getcwd())
    raise e
import rena.threadings.workers as workers
from rena.ui.StreamWidget import StreamWidget
from rena.ui.RecordingsTab import RecordingsTab
from rena.ui.SettingsTab import SettingsTab
from rena.ui.ReplayTab import ReplayTab
from rena.utils.data_utils import window_slice
from rena.utils.general import process_preset_create_openBCI_interface_startsensor, \
    process_preset_create_TImmWave_interface_startsensor
from rena.utils.ui_utils import dialog_popup, \
    init_camera_widget, convert_rgb_to_qt_image, another_window

import numpy as np
import collections


# Define function to import external files when using PyInstaller.
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


class MainWindow(QtWidgets.QMainWindow):

    def __init__(self, app, ask_to_close=True, *args, **kwargs):
        """
        This is the main entry point to RenaLabApp
        :param app: the main QT app
        :param ask_to_close: whether to show a 'confirm exit' dialog and ask for
         user's confirmation in a close event
        :param args:
        :param kwargs:
        """
        super().__init__(*args, **kwargs)
        self.ui = uic.loadUi("ui/mainwindow.ui", self)
        self.setWindowTitle('Reality Navigation')
        self.app = app
        self.ask_to_close = ask_to_close

        ############
        self.stream_widgets = {}  # key: stream -> value: stream_widget
        self.video_device_widgets = {}  # key: stream -> value: stream_widget
        ############

        # create sensor threads, worker threads for different sensors
        self.worker_threads = {}
        self.sensor_workers = {}
        self.device_workers = {}
        self.lsl_workers = {}
        self.inference_worker = None
        self.cam_workers = {}
        self.cam_displays = {}

        ######### init server
        print('Creating Rena Client')
        self.rena_dsp_client = RenaTCPInterface(stream_name=config.rena_server_name,
                                                port_id=config.rena_server_port,
                                                identity='client')

        #########

        self.lsl_replay_worker = None
        self.recent_visualization_refresh_timestamps = collections.deque(
            maxlen=config.VISUALIZATION_REFRESH_FREQUENCY_RETAIN_FRAMES)
        self.visualization_fps = 0
        self.tick_rate = 0

        # create workers for different sensors
        # camera/screen capture timer
        self.c_timer = QTimer()
        self.c_timer.setInterval(config.VIDEO_DEVICE_REFRESH_INTERVAL)  # for 15 Hz refresh rate
        self.c_timer.timeout.connect(self.camera_screen_capture_tick)
        self.c_timer.start()

        self.addStreamWidget = AddStreamWidget(self)
        self.MainTabVerticalLayout.insertWidget(0, self.addStreamWidget)  # add the add widget to visualization tab's
        self.addStreamWidget.add_btn.clicked.connect(self.add_btn_clicked)

        # data buffers
        self.LSL_plots_fs_label_dict = {}
        self.LSL_data_buffer_dicts = {}
        self.LSL_current_ts_dict = {}

        # scripting buffer
        self.inference_buffer = np.empty(shape=(0, config.INFERENCE_CLASS_NUM))  # time axis is the first

        # add other tabs
        self.recording_tab = RecordingsTab(self)
        self.recordings_tab_vertical_layout.addWidget(self.recording_tab)

        self.replay_tab = ReplayTab(self)
        self.replay_tab_vertical_layout.addWidget(self.replay_tab)

        self.scripting_tab = ScriptingTab(self)
        self.scripting_tab_vertical_layout.addWidget(self.scripting_tab)

        # windows
        self.pop_windows = {}
        self.test_ts_buffer = []

        # actions for context menu
        self.actionDocumentation.triggered.connect(self.fire_action_documentation)
        self.actionRepo.triggered.connect(self.fire_action_repo)
        self.actionShow_Recordings.triggered.connect(self.fire_action_show_recordings)
        self.actionExit.triggered.connect(self.fire_action_exit)
        self.actionSettings.triggered.connect(self.fire_action_settings)

        # create the settings window
        settings_tab = SettingsTab(self)
        self.settings_window = another_window('Settings')
        self.settings_window.get_layout().addWidget(settings_tab)
        self.settings_window.hide()


    def add_btn_clicked(self):
        """
        This should be the only entry point to adding a stream widget
        :return:
        """
        if self.recording_tab.is_recording:
            dialog_popup(msg='Cannot add while recording.')
            return
        selected_text, data_type, port, networking_interface = self.addStreamWidget.get_selected_stream_name(), \
                                                               self.addStreamWidget.get_data_type(), \
                                                               self.addStreamWidget.get_port_number(), \
                                                               self.addStreamWidget.get_networking_interface()
        if len(selected_text) == 0:
            return
        try:
            if selected_text in self.stream_widgets.keys():  # if this inlet hasn't been already added
                dialog_popup('Nothing is done for: {0}. This stream is already added.'.format(selected_text),title='Warning')
                return
            selected_type = self.addStreamWidget.get_current_selected_type()
            if selected_type == 'video':  # add video device
                self.init_video_device(selected_text)
            if selected_type == 'Device':  # if this is a device preset
                self.init_device(selected_text)  # add device stream
            elif selected_type == 'LSL' or selected_type == 'ZMQ':
                self.init_network_streaming(selected_text, networking_interface, data_type, port)  # add lsl stream
            elif selected_type == 'exp':  # add multiple streams from an experiment preset
                streams_for_experiment = get_experiment_preset_streams(selected_text)
                self.add_streams_to_visualize(streams_for_experiment)
            elif selected_type == 'other':  # add a previous unknown lsl stream
                self.create_preset(selected_text, data_type, port, networking_interface)
                self.scripting_tab.update_script_widget_input_combobox()  # add thew new preset to the combo box
                self.init_network_streaming(selected_text, data_type=data_type, port_number=port)  # TODO this can also be a device or experiment preset
            else: raise Exception("Unknow preset type {}".format(selected_type))
            self.update_num_active_stream_label()
        except RenaError as error:
            dialog_popup('Failed to add: {0}. {1}'.format(selected_text, str(error)), title='Error')
        self.addStreamWidget.check_can_add_input()

    def create_preset(self, stream_name, data_type, port, networking_interface, num_channels=1):
        create_default_preset(stream_name, data_type, port, networking_interface, num_channels)  # create the preset
        self.addStreamWidget.update_combobox_presets()  # add thew new preset to the combo box

    def remove_stream_widget(self, target):
        self.sensorTabSensorsHorizontalLayout.removeWidget(target)
        self.update_num_active_stream_label()
        self.addStreamWidget.check_can_add_input()  # check if the current selected preset has already been added

    def update_num_active_stream_label(self):
        available_widget_count = len([x for x in self.stream_widgets.values() if x.is_stream_available])
        streaming_widget_count = len([x for x in self.stream_widgets.values() if x.is_widget_streaming()])
        self.numActiveStreamsLabel.setText(
            num_active_streams_label_text.format(len(self.stream_widgets), available_widget_count,
                                                 streaming_widget_count, self.replay_tab.get_num_replay_channels()))

    def init_video_device(self, video_device_name):
        widget_name = video_device_name + '_widget'
        widget = VideoDeviceWidget(main_parent=self,
                                   parent_layout=self.sensorTabSensorsHorizontalLayout,
                                   video_device_name=video_device_name,
                                   insert_position=self.sensorTabSensorsHorizontalLayout.count() - 1)
        widget.setObjectName(widget_name)
        self.video_device_widgets[video_device_name] = widget


    def visualize_cam(self, cam_id_cv_img_timestamp):
        cam_id, cv_img, timestamp = cam_id_cv_img_timestamp
        if cam_id in self.cam_displays.keys():
            qt_img = convert_rgb_to_qt_image(cv_img)
            self.cam_displays[cam_id].setPixmap(qt_img)
            self.test_ts_buffer.append(time.time())
            self.recording_tab.update_camera_screen_buffer(cam_id, cv_img, timestamp)

    def add_streams_to_visualize(self, stream_names):

        for stream_name in stream_names:
            # check if the stream in setting's preset
            if check_preset_exists(stream_name):
                self.addStreamWidget.select_by_stream_name(stream_name)
                self.addStreamWidget.add_btn.click()
            else:  # add a new preset if the stream name is not defined
                self.addStreamWidget.set_selection_text(stream_name)
                self.addStreamWidget.add_btn.click()

        # loading_dlg.close()

    def add_streams_from_replay(self, stream_names):
        # switch tab to visulalization
        self.ui.tabWidget.setCurrentWidget(self.ui.tabWidget.findChild(QWidget, 'visualization_tab'))
        self.add_streams_to_visualize(stream_names)
        for stream_name in stream_names:
            if self.stream_widgets[stream_name].is_streaming():  # if not running click start stream
                self.stream_widgets[stream_name].StartStopStreamBtn.click()

    def init_network_streaming(self, networking_stream_name, networking_interface='LSL', data_type=None, port_number=None, worker=None):
        error_initialization = False

        # set up UI elements
        widget_name = networking_stream_name + '_widget'
        stream_widget = StreamWidget(main_parent=self,
                                     parent=self.sensorTabSensorsHorizontalLayout,
                                     stream_name=networking_stream_name,
                                     data_type=data_type,
                                     worker = worker,
                                     networking_interface=networking_interface,
                                     port_number=port_number,
                                     insert_position=self.sensorTabSensorsHorizontalLayout.count() - 1)
        start_stop_stream_btn, remove_stream_btn, pop_window_btn = stream_widget.StartStopStreamBtn, stream_widget.RemoveStreamBtn, stream_widget.PopWindowBtn
        stream_widget.setObjectName(widget_name)

        self.stream_widgets[networking_stream_name] = stream_widget

        if error_initialization:
            remove_stream_btn.click()
        config.settings.endGroup()

    def init_device(self, device_name):
        config.settings.beginGroup('presets/streampresets/{0}'.format(device_name))
        device_type = config.settings.value('DeviceType')

        if device_name not in self.device_workers.keys() and device_type == 'OpenBCI':
            serial_port = config.settings.value('_SerialPort')
            board_id = config.settings.value('_Board_id')
            # create and start this device's worker thread
            worker = workers.OpenBCIDeviceWorker(device_name, serial_port, board_id)
            config.settings.endGroup()
            self.init_network_streaming(device_name, networking_interface='Device', worker=worker)
        # TI mmWave connection

        # elif device_name not in self.device_workers.keys() and device_type == 'TImmWave_6843AOP':
        #     print('mmWave test')
        #     try:
        #         # mmWave connect, send config, start sensor
        #         num_range_bin = config.settings.value('NumRangeBin')
        #         Dport = config.settings.value['Dport(Standard)']
        #         Uport = config.settings.value['Uport(Enhanced)']
        #         config_path = config.settings.value['ConfigPath']
        #
        #         MmWaveSensorLSLInterface = process_preset_create_TImmWave_interface_startsensor(
        #             num_range_bin, Dport, Uport, config_path)
        #     except AssertionError as e:
        #         dialog_popup(str(e))
        #         config.settings.endGroup()
        #         return None
        #     self.device_workers[device_name] = workers.MmwWorker(mmw_interface=MmWaveSensorLSLInterface)
        #     worker_thread = pg.QtCore.QThread(self)
        #     self.worker_threads[device_name] = worker_thread
        #     self.device_workers[device_name].moveToThread(self.worker_threads[device_name])
        #     worker_thread.start()
        #     self.init_network_streaming(device_name)  # TODO test needed
        else:
            dialog_popup('We are not supporting this Device or the Device has been added')
        config.settings.endGroup()

    # def init_inference(self, inference_interface):
    #     inference_thread = pg.QtCore.QThread(self)
    #     self.worker_threads['scripting'] = inference_thread
    #     self.inference_worker = workers.InferenceWorker(inference_interface)
    #     self.inference_worker.moveToThread(self.worker_threads['scripting'])
    #     self.init_visualize_inference_results()
    #     self.inference_worker.signal_inference_results.connect(self.visualize_inference_results)
    #
    #     self.connect_inference_btn.clicked.connect(self.inference_worker.connect)
    #     self.disconnect_inference_btn.clicked.connect(self.inference_worker.disconnect)
    #
    #     # self.connect_inference_btn.setStyleSheet(config_ui.inference_button_style)
    #     inference_thread.start()
    #     self.inference_widget.hide()

    # def inference_ticks(self):
    #     # only ticks if data is streaming
    #     if 'Unity.ViveSREyeTracking' in self.lsl_workers.keys() and self.inference_worker:
    #         if self.lsl_workers['Unity.ViveSREyeTracking'].is_streaming:
    #             buffered_data = self.LSL_data_buffer_dicts['Unity.ViveSREyeTracking']
    #             if buffered_data.shape[-1] < config.EYE_INFERENCE_TOTAL_TIMESTEPS:
    #                 eye_frames = np.concatenate((np.zeros(shape=(
    #                     2,  # 2 for two eyes' pupil sizes
    #                     config.EYE_INFERENCE_TOTAL_TIMESTEPS - buffered_data.shape[-1])),
    #                                              buffered_data[2:4, :]), axis=-1)
    #             else:
    #                 eye_frames = buffered_data[1:3,
    #                              -config.EYE_INFERENCE_TOTAL_TIMESTEPS:]
    #             # make samples out of the most recent data
    #             eye_samples = window_slice(eye_frames, window_size=config.EYE_INFERENCE_WINDOW_TIMESTEPS,
    #                                        stride=config.EYE_WINDOW_STRIDE_TIMESTEMPS, channel_mode='channel_first')
    #
    #             samples_dict = {'eye': eye_samples}
    #             self.inference_worker.signal_data_tick.emit(samples_dict)

    def camera_screen_capture_tick(self):
        [w.signal_data_tick.emit() for w in self.cam_workers.values()]

    def reload_all_presets_btn_clicked(self):
        if self.reload_all_presets():
            self.update_presets_combo_box()
            dialog_popup('Reloaded all presets', title='Info')

    def update_presets_combo_box(self):
        self.preset_LSLStream_combo_box.clear()
        self.preset_LSLStream_combo_box.addItems(self.lslStream_presets_dict.keys())
        self.device_combo_box.clear()
        self.device_combo_box.addItems(self.device_presets_dict.keys())
        self.experiment_combo_box.clear()
        self.experiment_combo_box.addItems(self.experiment_presets_dict.keys())

    def closeEvent(self, event):
        if self.ask_to_close:
            reply = QMessageBox.question(self, 'Window Close', 'Exit Application?',
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        else:
            reply = QMessageBox.Yes
        if reply == QMessageBox.Yes:
            if self.settings_window is not None:
                self.settings_window.close()
            remove_btns = [x.RemoveStreamBtn for x in self.stream_widgets.values()]
            [x.click() for x in remove_btns]

            # close other tabs
            self.scripting_tab.try_close()
            self.replay_tab.try_close()

            event.accept()
            self.app.quit()
        else:
            event.ignore()

    def fire_action_documentation(self):
        webbrowser.open("https://realitynavigationdocs.readthedocs.io/")

    def fire_action_repo(self):
        webbrowser.open("https://github.com/ApocalyVec/RealityNavigation")

    def fire_action_show_recordings(self):
        self.recording_tab.open_recording_directory()

    def fire_action_exit(self):
        self.close()

    def fire_action_settings(self):
        self.settings_window.show()
        self.settings_window.activateWindow()

    def get_added_stream_names(self):
        return list(self.stream_widgets.keys()) + list(self.cam_workers.keys())
