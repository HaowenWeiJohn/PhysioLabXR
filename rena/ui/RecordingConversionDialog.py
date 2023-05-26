import pickle

from PyQt5 import QtWidgets, uic
from PyQt5.QtCore import QObject, pyqtSignal, QThread
import pyqtgraph as pg
from scipy.io import savemat
import numpy as np
import os
import csv

from rena.configs.configs import RecordingFileFormat
from rena.utils.data_utils import RNStream


class RecordingConversionDialog(QtWidgets.QWidget):
    def __init__(self,  file_path, file_format: RecordingFileFormat):
        super().__init__()
        self.ui = uic.loadUi("ui/RecordingConversionDialog.ui", self)
        self.setWindowTitle('Please wait for file conversion')

        self.file_format = file_format
        self.file_path = file_path

        self.recording_convertion_worker = RecordingConversionWorker(RNStream(file_path), file_format, file_path)
        self.thread = QThread()
        self.thread.started.connect(self.recording_convertion_worker.run)
        self.recording_convertion_worker.moveToThread(self.thread)

        self.recording_convertion_worker.progress.connect(self.conversion_progress)
        self.recording_convertion_worker.finished_streamin.connect(self.streamin_finished)
        self.recording_convertion_worker.finished_conversion.connect(self.conversion_finished)

        self.finish_button.clicked.connect(self.on_finish_button_clicked)
        self.finish_button.hide()

        self.thread.start()

    def conversion_finished(self, newfile_path):
        print('Conversion finished, showing the finish button')
        self.progress_label.setText('Complete saving file to {}'.format(newfile_path))
        self.finish_button.show()

    def conversion_progress(self, progresses):
        read_bytes, total_bytes = progresses
        self.progress_label.setText('Loading file back in: {} % loaded'.format(str(round(100 * read_bytes/total_bytes, 2))))
        self.progress_label.repaint()
        # print('updated progress label')

    def streamin_finished(self):
        self.progress_label.setText('Converting to {}'.format(self.file_format))

    def on_finish_button_clicked(self):
        self.close()
        self.thread.quit()


class RecordingConversionWorker(QObject):
    finished_streamin = pyqtSignal()
    finished_conversion = pyqtSignal(str)
    progress = pyqtSignal(list)

    def __init__(self, stream, file_format: RecordingFileFormat, file_path):
        super().__init__()
        self.stream = stream
        self.file_format = file_format
        self.file_path = file_path

    def run(self):
        print("RecordingConversionWorker started running")
        file, buffer, read_bytes_count = None, None, None
        while True:
            file, buffer, read_bytes_count, total_bytes, finished = self.stream.stream_in_stepwise(file, buffer, read_bytes_count, jitter_removal=False)
            if finished:
                break
            self.progress.emit([read_bytes_count, total_bytes])
        self.finished_streamin.emit()

        newfile_path = self.file_path
        if self.file_format == RecordingFileFormat.matlab:
            newfile_path = self.file_path.replace('.dats', '.m')
            savemat(newfile_path, buffer, oned_as='row')
        elif self.file_format == RecordingFileFormat.pickle:
            newfile_path = self.file_path.replace('.dats', '.p')
            pickle.dump(buffer, open(newfile_path, 'wb'))
        elif self.file_format == "Comma separate values (.CSV)":
            if not os.path.exists(self.file_path.replace('.dats', '')):
                newfile_path = os.mkdir(self.file_path.replace('.dats', ''))
            for key, value in buffer.items():
                # np.savetxt(os.path.join(self.file_path.replace('.dats', ''), f'{key}_y.csv'), value[0], delimiter=',') if (value[0].ndim <= 2) else np.savetxt(os.path.join(self.file_path.replace('.dats', ''), f'{key}_y.csv'), np.reshape(buffer['monitor 0'][0],(buffer['monitor 0'][0].shape[0]*buffer['monitor 0'][0].shape[2], buffer['monitor 0'][0].shape[1]*buffer['monitor 0'][0].shape[3])), delimiter=',')
                if value[0].ndim <= 2:
                    np.savetxt(os.path.join(self.file_path.replace('.dats', ''), f'{key}_y.csv'), np.append(value[0], np.reshape(value[1], (1, -1)), axis=0), delimiter=',')
                elif key == 'monitor 0':
                    shape_0 = value[0].shape[0] * value[0].shape[2]
                    shape_1 = value[0].shape[1] * value[0].shape[3]
                    np.savetxt(os.path.join(self.file_path.replace('.dats', ''), f'{key}.csv'), np.reshape(value[0], (shape_0, shape_1)), delimiter=',', fmt='%d')
                    with open(os.path.join(self.file_path.replace('.dats', ''), f'{key}.csv'), 'a', newline='') as csvfile:
                        writer = csv.writer(csvfile)
                        writer.writerow(value[1])
                        writer.writerow(value[0].shape)
                else:
                    raise Exception(f"Unknown stream data shape")

        else:
            raise NotImplementedError
        self.finished_conversion.emit(newfile_path)