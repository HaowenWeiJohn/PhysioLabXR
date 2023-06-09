import os
import warnings
from pathlib import Path
from datetime import datetime
import csv

import cv2
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import resample
from scipy.stats import stats

from exceptions.exceptions import BadOutputError
from rena.utils.Singleton import Singleton
from rena.utils.sig_proc_utils import baseline_correction, notch_filter


def window_slice(data, window_size, stride, channel_mode='channel_last'):
    assert len(data.shape) == 2
    if channel_mode == 'channel_first':
        data = np.transpose(data)
    elif channel_mode == 'channel_last':
        pass
    else:
        raise Exception('Unsupported channel mode')
    assert window_size <= len(data)
    assert stride > 0
    rtn = np.expand_dims(data, axis=0) if window_size == len(data) else []
    for i in range(window_size, len(data), stride):
        rtn.append(data[i - window_size:i])
    return np.array(rtn)


# constant
magic = b'\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\x0c\r\x0e\x0f'
max_label_len = 32
max_dtype_len = 8
dim_bytes_len = 8
shape_bytes_len = 8

endianness = 'little'
encoding = 'utf-8'

ts_dtype = 'float64'


class RNStream:
    def __init__(self, file_path):
        self.fn = file_path

    def stream_out(self, buffer):
        """
        serialize the content of the buffer to the file path pointed by self.fn
        :param buffer: a dictionary, key is a string for stream name, value is a iterable of two ndarray
                        the first of the two ndarray is the data samples, the second of the two ndarray are the timestamps
                        of the data samples. The time axis for the data array must be the last. The timestamp array must
                         have exactly one dimension (the time dimension). The data and timestamps
                        array must have the same length in their time dimensions.
                        The timestamps array must also in a increasing order, otherwise a warning will be raised
        :return: the total number of byptes that has been streamed out
        """
        out_file = open(self.fn, "ab")
        stream_label_bytes, dtype_bytes, dim_bytes, shape_bytes, data_bytes, ts_bytes = \
            b'', b'', b'', b'', b'', b''
        total_bytes = 0
        for stream_label, data_ts_array in buffer.items():
            data_array, ts_array = data_ts_array[0], data_ts_array[1]

            # cast the arrays in
            if type(data_array) != np.ndarray:
                data_array = np.array(data_array)
            if type(ts_array) != np.ndarray:
                ts_array = np.array(ts_array)

            try:
                assert len(ts_array.shape) == 1
            except AssertionError:
                raise Exception('timestamps must have exactly one dimension.')

            try:
                assert all(i < j for i, j in zip(ts_array, ts_array[1:]))
            except AssertionError:
                warnings.warn(f'RNStream: [{stream_label}] timestamps must be in increasing order.', UserWarning)
            stream_label_bytes = \
                bytes(stream_label[:max_label_len] + "".join(
                    " " for x in range(max_label_len - len(stream_label))), encoding)
            try:
                dtype_str = str(data_array.dtype)
                assert len(dtype_str) < max_dtype_len
            except AssertionError:
                raise Exception('dtype encoding exceeds max dtype length: {0}, please contact support'.format(max_dtype_len))
            dtype_bytes = bytes(dtype_str + "".join(" " for x in range(max_dtype_len - len(dtype_str))),
                                encoding)
            try:
                dim_bytes = len(data_array.shape).to_bytes(dim_bytes_len, 'little')
                shape_bytes = b''.join(
                    [s.to_bytes(shape_bytes_len, 'little') for s in data_array.shape])  # the last axis is time
            except OverflowError:
                raise Exception('RN requires its stream to have number of dimensions less than 2^40, '
                                'and the size of any dimension to be less than the same number ')
            data_bytes = data_array.tobytes()
            ts_bytes = ts_array.tobytes()
            out_file.write(magic)
            out_file.write(stream_label_bytes)
            out_file.write(dtype_bytes)
            out_file.write(dim_bytes)
            out_file.write(shape_bytes)
            out_file.write(data_bytes)
            out_file.write(ts_bytes)
            total_bytes += len(magic) + len(stream_label_bytes) + len(dtype_bytes) + len(dim_bytes) + len(shape_bytes) + len(data_bytes) + len(ts_bytes)
        out_file.close()
        return total_bytes

    def stream_in(self, ignore_stream=None, only_stream=None, jitter_removal=True, reshape_stream_dict=None):
        """
        different from LSL XDF importer, this jitter removal assumes no interruption in the data
        :param ignore_stream:
        :param only_stream:
        :param jitter_removal:
        :param reshape_stream_dict:
        :return:
        """
        total_bytes = float(os.path.getsize(self.fn))  # use floats to avoid scalar type overflow
        buffer = {}
        read_bytes_count = 0.
        with open(self.fn, "rb") as file:
            while True:
                if total_bytes:
                    print('Streaming in progress {0}%'.format(str(round(100 * read_bytes_count/total_bytes, 2))), sep=' ', end='\r', flush=True)
                # read magic
                read_bytes = file.read(len(magic))
                read_bytes_count += len(read_bytes)
                if len(read_bytes) == 0:
                    break
                try:
                    assert read_bytes == magic
                except AssertionError:
                    raise Exception('Data invalid, magic sequence not found')
                # read stream_label
                read_bytes = file.read(max_label_len)
                read_bytes_count += len(read_bytes)
                stream_name = str(read_bytes, encoding).strip(' ')
                # read read_bytes
                read_bytes = file.read(max_dtype_len)
                read_bytes_count += len(read_bytes)
                stream_dytpe = str(read_bytes, encoding).strip(' ')
                # read number of dimensions
                read_bytes = file.read(dim_bytes_len)
                read_bytes_count += len(read_bytes)
                dims = int.from_bytes(read_bytes, 'little')
                # read number of np shape
                shape = []
                for i in range(dims):
                    read_bytes = file.read(shape_bytes_len)
                    read_bytes_count += len(read_bytes)
                    shape.append(int.from_bytes(read_bytes, 'little'))

                data_array_num_bytes = np.prod(shape) * np.dtype(stream_dytpe).itemsize
                timestamp_array_num_bytes = shape[-1] * np.dtype(ts_dtype).itemsize

                this_in_only_stream = (stream_name in only_stream) if only_stream else True
                not_ignore_this_stream = (stream_name not in ignore_stream) if ignore_stream else True
                if not_ignore_this_stream and this_in_only_stream:
                    # read data array
                    read_bytes = file.read(data_array_num_bytes)
                    read_bytes_count += len(read_bytes)
                    data_array = np.frombuffer(read_bytes, dtype=stream_dytpe)
                    data_array = np.reshape(data_array, newshape=shape)
                    # read timestamp array
                    read_bytes = file.read(timestamp_array_num_bytes)
                    ts_array = np.frombuffer(read_bytes, dtype=ts_dtype)

                    if stream_name not in buffer.keys():
                        buffer[stream_name] = [np.empty(shape=tuple(shape[:-1]) + (0,), dtype=stream_dytpe),
                                               np.empty(shape=(0,))]  # data first, timestamps second
                    buffer[stream_name][0] = np.concatenate([buffer[stream_name][0], data_array], axis=-1)
                    buffer[stream_name][1] = np.concatenate([buffer[stream_name][1], ts_array])
                else:
                    file.read(data_array_num_bytes + timestamp_array_num_bytes)
                    read_bytes_count += data_array_num_bytes + timestamp_array_num_bytes
        if jitter_removal:
            i = 1
            for stream_name, (d_array, ts_array) in buffer.items():
                if len(ts_array) < 2:
                    print("Ignore jitter remove for stream {0}, because it has fewer than two samples".format(stream_name))
                    continue
                if np.std(ts_array) > 0.1:
                    warnings.warn("Stream {0} may have a irregular sampling rate with std {0}. Jitter removal should not be applied to irregularly sampled streams.".format(stream_name, np.std(ts_array)), RuntimeWarning)
                print('Removing jitter for streams {0}/{1}'.format(i, len(buffer)), sep=' ',
                      end='\r', flush=True)
                coefs = np.polyfit(list(range(len(ts_array))), ts_array, 1)
                smoothed_ts_array = np.array([i * coefs[0] + coefs[1] for i in range(len(ts_array))])
                buffer[stream_name][1] = smoothed_ts_array

        # reshape img, time series, time frames data
        if reshape_stream_dict is not None:
            for reshape_stream_name in reshape_stream_dict:
                if reshape_stream_name in buffer:  # reshape the stream[0] to [(a,b,c), (d, e), x, y] etc

                    shapes = reshape_stream_dict[reshape_stream_name]
                    # check if the number of channel matches the number of reshape channels
                    total_reshape_channel_num = 0
                    for shape_item in shapes: total_reshape_channel_num += np.prod(shape_item)
                    if total_reshape_channel_num == buffer[reshape_stream_name][0].shape[0]:
                        # number of channels matches, start reshaping
                        reshape_data_buffer = {}
                        offset = 0
                        for index, shape_item in enumerate(shapes):
                            reshape_channel_num = np.prod(shape_item)
                            data_slice = buffer[reshape_stream_name][0][offset:offset + reshape_channel_num,
                                         :]  # get the slice
                            # reshape all column to shape_item
                            print((shape_item + (-1,)))
                            data_slice = data_slice.reshape((shape_item + (-1,)))
                            reshape_data_buffer[index] = data_slice
                            offset += reshape_channel_num

                        #     replace buffer[stream_name][0] with new reshaped buffer
                        buffer[reshape_stream_name][0] = reshape_data_buffer

                    else:
                        raise Exception(
                            'Error: The given total number of reshape channel does not match the total number of saved '
                            'channel for stream: ({0})'.format(reshape_stream_name))

                else:
                    raise Exception(
                        'Error: The give target reshape stream ({0}) does not exist in the data buffer, please use ('
                        'get_stream_names) function to check the stream names'.format(reshape_stream_name))

        print("Stream-in completed: {0}".format(self.fn))
        return buffer

    def stream_in_stepwise(self, file, buffer, read_bytes_count, ignore_stream=None, only_stream=None, jitter_removal=True, reshape_stream_dict=None):
        total_bytes = float(os.path.getsize(self.fn))  # use floats to avoid scalar type overflow
        buffer = {} if buffer is None else buffer
        read_bytes_count = 0. if read_bytes_count is None else read_bytes_count
        file = open(self.fn, "rb") if file is None else file
        finished = False

        if total_bytes:
            print('Streaming in progress {0}%'.format(str(round(100 * read_bytes_count/total_bytes, 2))), sep=' ', end='\r', flush=True)
        # read magic
        read_bytes = file.read(len(magic))
        read_bytes_count += len(read_bytes)
        if len(read_bytes) == 0:
            finished = True
        if not finished:
            try:
                assert read_bytes == magic
            except AssertionError:
                raise Exception('Data invalid, magic sequence not found')
            # read stream_label
            read_bytes = file.read(max_label_len)
            read_bytes_count += len(read_bytes)
            stream_name = str(read_bytes, encoding).strip(' ')
            # read read_bytes
            read_bytes = file.read(max_dtype_len)
            read_bytes_count += len(read_bytes)
            stream_dytpe = str(read_bytes, encoding).strip(' ')
            # read number of dimensions
            read_bytes = file.read(dim_bytes_len)
            read_bytes_count += len(read_bytes)
            dims = int.from_bytes(read_bytes, 'little')
            # read number of np shape
            shape = []
            for i in range(dims):
                read_bytes = file.read(shape_bytes_len)
                read_bytes_count += len(read_bytes)
                shape.append(int.from_bytes(read_bytes, 'little'))

            data_array_num_bytes = np.prod(shape) * np.dtype(stream_dytpe).itemsize
            timestamp_array_num_bytes = shape[-1] * np.dtype(ts_dtype).itemsize

            this_in_only_stream = (stream_name in only_stream) if only_stream else True
            not_ignore_this_stream = (stream_name not in ignore_stream) if ignore_stream else True
            if not_ignore_this_stream and this_in_only_stream:
                # read data array
                read_bytes = file.read(data_array_num_bytes)
                read_bytes_count += len(read_bytes)
                data_array = np.frombuffer(read_bytes, dtype=stream_dytpe)
                data_array = np.reshape(data_array, newshape=shape)
                # read timestamp array
                read_bytes = file.read(timestamp_array_num_bytes)
                ts_array = np.frombuffer(read_bytes, dtype=ts_dtype)

                if stream_name not in buffer.keys():
                    buffer[stream_name] = [np.empty(shape=tuple(shape[:-1]) + (0,), dtype=stream_dytpe),
                                           np.empty(shape=(0,))]  # data first, timestamps second
                buffer[stream_name][0] = np.concatenate([buffer[stream_name][0], data_array], axis=-1)
                buffer[stream_name][1] = np.concatenate([buffer[stream_name][1], ts_array])
            else:
                file.read(data_array_num_bytes + timestamp_array_num_bytes)
                read_bytes_count += data_array_num_bytes + timestamp_array_num_bytes
        if finished:
            if jitter_removal:
                i = 1
                for stream_name, (d_array, ts_array) in buffer.items():
                    if len(ts_array) < 2:
                        print("Ignore jitter remove for stream {0}, because it has fewer than two samples".format(stream_name))
                        continue
                    if np.std(ts_array) > 0.1:
                        warnings.warn("Stream {0} may have a irregular sampling rate with std {0}. Jitter removal should not be applied to irregularly sampled streams.".format(stream_name, np.std(ts_array)), RuntimeWarning)
                    print('Removing jitter for streams {0}/{1}'.format(i, len(buffer)), sep=' ',
                          end='\r', flush=True)
                    coefs = np.polyfit(list(range(len(ts_array))), ts_array, 1)
                    smoothed_ts_array = np.array([i * coefs[0] + coefs[1] for i in range(len(ts_array))])
                    buffer[stream_name][1] = smoothed_ts_array

            # reshape img, time series, time frames data
            if reshape_stream_dict is not None:
                for reshape_stream_name in reshape_stream_dict:
                    if reshape_stream_name in buffer:  # reshape the stream[0] to [(a,b,c), (d, e), x, y] etc

                        shapes = reshape_stream_dict[reshape_stream_name]
                        # check if the number of channel matches the number of reshape channels
                        total_reshape_channel_num = 0
                        for shape_item in shapes: total_reshape_channel_num += np.prod(shape_item)
                        if total_reshape_channel_num == buffer[reshape_stream_name][0].shape[0]:
                            # number of channels matches, start reshaping
                            reshape_data_buffer = {}
                            offset = 0
                            for index, shape_item in enumerate(shapes):
                                reshape_channel_num = np.prod(shape_item)
                                data_slice = buffer[reshape_stream_name][0][offset:offset + reshape_channel_num,
                                             :]  # get the slice
                                # reshape all column to shape_item
                                print((shape_item + (-1,)))
                                data_slice = data_slice.reshape((shape_item + (-1,)))
                                reshape_data_buffer[index] = data_slice
                                offset += reshape_channel_num

                            #     replace buffer[stream_name][0] with new reshaped buffer
                            buffer[reshape_stream_name][0] = reshape_data_buffer

                        else:
                            raise Exception(
                                'Error: The given total number of reshape channel does not match the total number of saved '
                                'channel for stream: ({0})'.format(reshape_stream_name))

                    else:
                        raise Exception(
                            'Error: The give target reshape stream ({0}) does not exist in the data buffer, please use ('
                            'get_stream_names) function to check the stream names'.format(reshape_stream_name))

        return file, buffer, read_bytes_count, total_bytes, finished

    def get_stream_names(self):
        total_bytes = float(os.path.getsize(self.fn))  # use floats to avoid scalar type overflow
        stream_names = []
        read_bytes_count = 0.
        with open(self.fn, "rb") as file:
            while True:
                print('Scanning stream in progress {}%'.format(str(round(100 * read_bytes_count / total_bytes, 2))),
                      sep=' ', end='\r', flush=True)
                # read magic
                read_bytes = file.read(len(magic))
                read_bytes_count += len(read_bytes)
                if len(read_bytes) == 0:
                    break
                try:
                    assert read_bytes == magic
                except AssertionError:
                    raise Exception('Data invalid, magic sequence not found')
                # read stream_label
                read_bytes = file.read(max_label_len)
                read_bytes_count += len(read_bytes)
                stream_label = str(read_bytes, encoding).strip(' ')
                # read read_bytes
                read_bytes = file.read(max_dtype_len)
                read_bytes_count += len(read_bytes)
                stream_dytpe = str(read_bytes, encoding).strip(' ')
                # read number of dimensions
                read_bytes = file.read(dim_bytes_len)
                read_bytes_count += len(read_bytes)
                dims = int.from_bytes(read_bytes, 'little')
                # read number of np shape
                shape = []
                for i in range(dims):
                    read_bytes = file.read(shape_bytes_len)
                    read_bytes_count += len(read_bytes)
                    shape.append(int.from_bytes(read_bytes, 'little'))

                data_array_num_bytes = np.prod(shape) * np.dtype(stream_dytpe).itemsize
                timestamp_array_num_bytes = shape[-1] * np.dtype(ts_dtype).itemsize

                file.read(data_array_num_bytes + timestamp_array_num_bytes)
                read_bytes_count += data_array_num_bytes + timestamp_array_num_bytes

                stream_names.append(stream_label)
        print("Scanning stream completed: {0}".format(self.fn))
        return stream_names

    def generate_video(self, video_stream_name, output_path=''):
        """
        if output path is not specified, the output video will be place in the same directory as the
        stream .dats file with a tag to its stream name
        :param stream_name:
        :param output_path:
        """
        print('Load video stream...')
        data_fn = self.fn.split('/')[-1]
        data_root = Path(self.fn).parent.absolute()
        data = self.stream_in(only_stream=(video_stream_name,))

        video_frame_stream = data[video_stream_name][0]
        frame_count = video_frame_stream.shape[-1]

        timestamp_stream = data[video_stream_name][1]
        frate = len(timestamp_stream) / (timestamp_stream[-1] - timestamp_stream[0])
        try:
            assert len(video_frame_stream.shape) == 4 and video_frame_stream.shape[2] == 3
        except AssertionError:
            raise Exception('target stream is not a video stream. It does not have 4 dims (height, width, color, time)'
                            'and/or the number of its color channel does not equal 3.')
        frame_size = (data[video_stream_name][0].shape[1], data[video_stream_name][0].shape[0])
        output_path = os.path.join(data_root, '{0}_{1}.avi'.format(data_fn.split('.')[0], video_stream_name)) if output_path == '' else output_path

        out = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*'DIVX'),frate, frame_size)

        for i in range(frame_count):
            print('Creating video progress {}%'.format(str(round(100 * i / frame_count, 2))), sep=' ', end='\r',
                  flush=True)
            img = video_frame_stream[:, :, :, i]
            # img = np.reshape(img, newshape=list(frame_size) + [-1,])
            out.write(img)

        out.release()


def plot_stream(stream, timestamps):
    timestamps = timestamps - timestamps[0]  # baseline the timestamps
    plt.plot(timestamps, stream)
    plt.xlabel('Time (sec)')
    plt.show()


def modify_indice_to_cover(i1, i2, coverage, tolerance=3):
    assert i1 < i2
    assert abs(coverage - (i2 - i1)) <= tolerance
    is_modifying_i1 = True
    if i2 - i1 > coverage:
        while i2 - i1 != coverage:
            if is_modifying_i1:
                i1 += 1
            else:
                i2 -= 1
        print('Modified')

    elif i2 - i1 < coverage:
        while i2 - i1 != coverage:
            if is_modifying_i1:
                i1 -= 1
            else:
                i2 += 1
        print('Modified')

    return i1, i2


def process_data(file_path, EM_stream_name, EEG_stream_name, target_labels, pre_stimulus_time, post_stimulus_time,
                 EEG_stream_preset, notch_f0=60., notch_band_demoninator=200, EEG_fresample=50, baselining=True):
    EEG_num_sample_per_trail = int(EEG_stream_preset['NominalSamplingRate'] * (post_stimulus_time - pre_stimulus_time))
    EEG_num_sample_per_trail_RESAMPLED = int(EEG_fresample * (post_stimulus_time - pre_stimulus_time))
    EEG_num_chan = EEG_stream_preset['GroupInfo'][1] - EEG_stream_preset['GroupInfo'][0]
    epoched_EEG = np.empty(shape=(0, EEG_num_chan, EEG_num_sample_per_trail))

    for fp in file_path:

        rns = RNStream(fp)
        data = rns.stream_in(ignore_stream=('monitor1', '0'))
        # plot_stream(data['Unity.VisualSearch.EventMarkers'][0][-1, :], data['Unity.VisualSearch.EventMarkers'][1])
        # plot_stream(data['Unity.RotationWheel.EventMarkers'][0][-1, :], data['Unity.RotationWheel.EventMarkers'][1])

        # get all needed streams ##########################################################################
        '''
        EM = Event Marker
        '''
        stream_EM = data[EM_stream_name][0]
        timestamps_EM = data[EM_stream_name][1]
        stream_EEG = data[EEG_stream_name][0]
        timestamps_EEG = data[EEG_stream_name][1]

        array_event_label = stream_EM[-1, :]

        # event label sanity check #############################################################################################
        # target_label = 1
        # target_onset_em = np.logical_and(event_label_stream == target_label, np.concatenate([np.array([0]), np.diff(event_label_stream)]) != 0)
        # plt.scatter(timestamps_stream, target_onset_em, c='r')
        #
        # target_label = 3
        # target_onset_em = np.logical_and(event_label_stream == target_label, np.concatenate([np.array([0]), np.diff(event_label_stream)]) != 0)
        # plt.scatter(timestamps_stream, target_onset_em, c='b')
        # plt.show()

        # take out the electrode channels
        stream_EEG_preprocessed = stream_EEG[
                                  EEG_stream_preset['GroupInfo'][0]:EEG_stream_preset['GroupInfo'][1],
                                  :]
        # baseline correction
        if baselining:
            print('Performing baseline correction, this may take a while')
            stream_EEG_preprocessed = baseline_correction(stream_EEG_preprocessed, lam=10, p=0.05)

        for tl in target_labels:
            array_target_onset_EM_indices = np.logical_and(array_event_label == tl,
                                                           np.concatenate([np.array([0]), np.diff(array_event_label)]) != 0)
            print('Number of trials is {0} for label {1}'.format(np.count_nonzero(array_target_onset_EM_indices), tl))
            array_target_PRE_onset_EM_timestamps = timestamps_EM[array_target_onset_EM_indices] + pre_stimulus_time
            array_target_onset_EM_timestamps = timestamps_EM[array_target_onset_EM_indices]
            array_target_POST_onset_EM_timestamps = timestamps_EM[array_target_onset_EM_indices] + post_stimulus_time

            # preprocess eeg ##############################################################################################
            # notch filter
            stream_EEG_preprocessed = notch_filter(stream_EEG_preprocessed, notch_f0, notch_f0 / notch_band_demoninator,
                                                   EEG_stream_preset['NominalSamplingRate'], channel_format='first')

            # find the nearest timestamp index in eeg #####################################################
            array_target_PRE_onset_EEG_indices = np.array(
                [(np.abs(timestamps_EEG - x)).argmin() for x in array_target_PRE_onset_EM_timestamps])
            array_target_onset_EEG_indices = np.array(
                [(np.abs(timestamps_EEG - x)).argmin() for x in array_target_onset_EM_timestamps])
            array_target_POST_onset_EEG_indices = np.array(
                [(np.abs(timestamps_EEG - x)).argmin() for x in array_target_POST_onset_EM_timestamps])

            array_target_onset_EEG_timestamps = timestamps_EEG[array_target_onset_EEG_indices]
            print('EM-EEG target onset timestamp discrepency: mean {0}, std {1}'.format(
                np.mean(array_target_onset_EM_timestamps - array_target_onset_EEG_timestamps),
                np.std(array_target_onset_EM_timestamps - array_target_onset_EEG_timestamps)))

            # epoch eeg data #############################################
            # modify pre and post indices for possible remaining jitter

            array_prepost_target_onset_i = [modify_indice_to_cover(pre_onset_i, post_onset_i, EEG_num_sample_per_trail)
                                            for
                                            pre_onset_i, post_onset_i in
                                            zip(array_target_PRE_onset_EEG_indices,
                                                array_target_POST_onset_EEG_indices)]
            epoched_EEG_new = np.array(
                [stream_EEG_preprocessed[:, pre_onset_i:post_onset_i] for pre_onset_i, post_onset_i in
                 array_prepost_target_onset_i])
            epoched_EEG = np.concatenate([epoched_EEG, epoched_EEG_new], axis=0)
        print('Total number of trials for label {0} is {1}'.format(str(target_labels), len(epoched_EEG)))

    # down sample the epoch eeg
    epoched_EEG_RESAMPLED = resample(epoched_EEG, EEG_num_sample_per_trail_RESAMPLED, axis=-1)

    # averaging
    epoched_EEG_average_trial = np.mean(epoched_EEG_RESAMPLED, axis=0)
    epoched_EEG_average_trial_chan = np.mean(epoched_EEG_average_trial, axis=0)

    epoched_EEG_max_trial = np.max(epoched_EEG_RESAMPLED, axis=0)
    epoched_EEG_max_trial_chan = np.max(epoched_EEG_max_trial, axis=0)

    epoched_EEG_min_trial = np.min(epoched_EEG_RESAMPLED, axis=0)
    epoched_EEG_min_trial_chan = np.min(epoched_EEG_min_trial, axis=0)

    epoched_EEG_timevector = np.linspace(pre_stimulus_time, post_stimulus_time, EEG_num_sample_per_trail_RESAMPLED)

    return epoched_EEG_timevector, epoched_EEG_average_trial_chan, epoched_EEG_max_trial_chan, epoched_EEG_min_trial_chan


def interp_negative(y):
    idx = y < 0
    x = np.arange(len(y))
    y_interp = np.copy(y)
    y_interp[idx] = np.interp(x[idx], x[~idx], y[~idx])
    return y_interp


def clutter_removal(cur_frame, clutter, signal_clutter_ratio):
    if clutter is None:
        clutter = cur_frame
    else:
        clutter = signal_clutter_ratio * clutter + (1 - signal_clutter_ratio) * cur_frame
    return cur_frame - clutter, clutter


def integer_one_hot(a, num_classes):
    a = a.astype(int)
    return np.squeeze(np.eye(num_classes)[a.reshape(-1)]).astype(int)


def corrupt_frame_padding(time_series_data, min_threshold=np.NINF, max_threshold=np.PINF, frame_channel_first=True):
    if not frame_channel_first:
        time_series_data = np.moveaxis(time_series_data, -1, 0)

    if np.min(time_series_data[0]) < min_threshold or np.max(time_series_data[0]) > max_threshold:
        print('error: first frame is broken')
        return

    if np.min(time_series_data[-1]) < min_threshold or np.max(time_series_data[-1]) > max_threshold:
        print('error: last frame is broken')
        return

    broken_frame_counter = 0

    # check first and last frame
    for frame_index in range(1, len(time_series_data) - 1):
        data = np.squeeze(time_series_data[frame_index], axis=-1)
        if np.min(time_series_data[frame_index]) < min_threshold or np.max(
                time_series_data[frame_index]) > max_threshold:
            # find broken frame, padding with frame +1 and frame -1
            broken_frame_before = time_series_data[frame_index - 1]
            broken_frame = time_series_data[frame_index]
            broken_frame_next = time_series_data[frame_index + 1]
            if np.min(time_series_data[frame_index + 1]) >= min_threshold and np.max(
                    time_series_data[frame_index + 1]) < max_threshold:
                time_series_data[frame_index] = (time_series_data[frame_index - 1] + time_series_data[
                    frame_index + 1]) * 0.5
                broken_frame_counter += 1
                print('find broken frame at index:', frame_index, ' interpolate by the frame before and after.')
            else:
                time_series_data[frame_index] = time_series_data[frame_index - 1]
                print('find two continues broken frames at index: ', frame_index, ', equalize with previous frame.')

    if not frame_channel_first:
        time_series_data = np.moveaxis(time_series_data, 0, -1)

    print('pad broken frame: ', broken_frame_counter)
    return time_series_data


def time_series_static_clutter_removal(time_series_data, init_clutter=None, signal_clutter_ratio=0.1,
                                       frame_channel_first=True):
    if not frame_channel_first:
        time_series_data = np.moveaxis(time_series_data, -1, 0)

    clutter = None
    if init_clutter:
        clutter = init_clutter
    else:  # using first two frames as the init_clutter
        clutter = (time_series_data[0] + time_series_data[1]) * 0.5

    for frame_index in range(0, len(time_series_data)):
        clutter_removal_frame, clutter = clutter_removal(
            cur_frame=time_series_data[frame_index],
            clutter=clutter,
            signal_clutter_ratio=signal_clutter_ratio)

        time_series_data[frame_index] = clutter_removal_frame

    if not frame_channel_first:
        time_series_data = np.moveaxis(time_series_data, 0, -1)

    return time_series_data

def is_broken_frame(frame, min_threshold=np.NINF, max_threshold=np.PINF):
    if np.min(frame) < min_threshold or np.max(frame) > max_threshold:
        return True
    else:
        return False


def levenshtein_ratio_and_distance(s, t, ratio_calc=False):
    """ levenshtein_ratio_and_distance:
        Calculates levenshtein distance between two strings.
        If ratio_calc = True, the function computes the
        levenshtein distance ratio of similarity between two strings
        For all i and j, distance[i,j] will contain the Levenshtein
        distance between the first i characters of s and the
        first j characters of t
    """
    # Initialize matrix of zeros
    rows = len(s) + 1
    cols = len(t) + 1
    distance = np.zeros((rows, cols), dtype=int)

    # Populate matrix of zeros with the indeces of each character of both strings
    for i in range(1, rows):
        for k in range(1, cols):
            distance[i][0] = i
            distance[0][k] = k

    # Iterate over the matrix to compute the cost of deletions,insertions and/or substitutions
    for col in range(1, cols):
        for row in range(1, rows):
            if s[row - 1] == t[col - 1]:
                cost = 0  # If the characters are the same in the two strings in a given position [i,j] then the cost is 0
            else:
                # In order to align the results with those of the Python Levenshtein package, if we choose to calculate the ratio
                # the cost of a substitution is 2. If we calculate just distance, then the cost of a substitution is 1.
                if ratio_calc == True:
                    cost = 2
                else:
                    cost = 1
            distance[row][col] = min(distance[row - 1][col] + 1,  # Cost of deletions
                                     distance[row][col - 1] + 1,  # Cost of insertions
                                     distance[row - 1][col - 1] + cost)  # Cost of substitutions
    if ratio_calc == True:
        # Computation of the Levenshtein Distance Ratio
        Ratio = ((len(s) + len(t)) - distance[row][col]) / (len(s) + len(t))
        return Ratio
    else:
        # print(distance) # Uncomment if you want to see the matrix showing how the algorithm computes the cost of deletions,
        # insertions and/or substitutions
        # This is the minimum number of edits needed to convert string a to string b
        return "The strings are {} edits away".format(distance[row][col])

def replace_special(target_str: str, replacement_dict):
    for special, replacement in replacement_dict.items():
        # print('replacing ' + special)
        target_str = target_str.replace(special, replacement)
    return target_str

# def dats_to_csv(buffer):
#     df = pd.DataFrame()
#     for stream_name, (data, timestamps) in buffer.items():
#         pass

def validate_output(data, expected_size):
    is_chunk = False

    if type(data) == list:
        try:
            assert is_homogeneous_type(data)
        except AssertionError:
            raise BadOutputError('Output data must be a homogeneous (all elements are of the same type) when given as a list')
        try:
            data = np.array(data)
        except np.VisibleDeprecationWarning:
            raise BadOutputError('Output data must not be a ragged list (containing sublist of different length) when given as a list')

    try:
        assert len(data.shape) == 2 or len(data.shape) == 1
    except AssertionError:
        raise BadOutputError('Output data must have one or two dimensions when given as a ndarray')
    if len(data.shape) == 2:
        try:
            assert data.shape[0] == expected_size or data.shape[1] == expected_size
        except AssertionError:
            raise BadOutputError(f'Out put data is two-dimensional with shape {data.shape}, one of the output\'s data dimension must be equal to the channel size {expected_size}')
        if data.shape[0] == expected_size:
            data = np.transpose(data)  #  the first dimension is the number of samples and the second is channels
        is_chunk = True
    else:  # if one-dimensional
        try:
            assert len(data) == expected_size
        except AssertionError:
            raise BadOutputError('Output data length {0} does not match the given size {1}'.format(len(data), expected_size))

    return data, is_chunk

def is_homogeneous_type(seq):
    iseq = iter(seq)
    first_type = type(next(iseq))
    return first_type if all( (type(x) is first_type) for x in iseq ) else False

def signal_generator(f, fs, duration, amp):
    wave = amp * (np.sin(2 * np.pi * np.arange(fs * duration) * f / fs)).astype(np.float32)
    return wave

def get_date_string():
    now = datetime.now()
    dt_string = now.strftime("%m_%d_%Y_%H_%M_%S")
    return dt_string

def mode_by_column(array: np.ndarray, ignore=None):
    assert len(array.shape) == 2
    rtn = []
    for i in range(array.shape[1]):
        mode = stats.mode(array[:, i][array[:, i] != ignore], axis=0).mode
        if len(mode) == 0:
            rtn.append(ignore)
        else:
            rtn.append(mode[0])
    return rtn

def camel_to_snake_case(camel_case_string):
    """
    Converts a string from camel case to snake case.

    Args:
        camel_string (str): The input string in camel case.

    Returns:
        str: The input string in snake case.
    """
    return ''.join(['_' + char.lower() if char.isupper() and i > 0 else char.lower() for i, char in enumerate(camel_case_string)])


def convert_dict_keys_to_snake_case(d: dict) -> dict:
    """
    Converts the keys of a dictionary from camel case to snake case.
    @param d:
    @return:
    """
    return {camel_to_snake_case(k): v for k, v in d.items()}

class CsvStoreLoad:
    def __init__(self):
        self.path = None
    def store_csv(self, data, file_path):
        if not os.path.exists(file_path.replace('.dats', '')):
            newfile_path = file_path.replace('.dats', '')
            os.mkdir(newfile_path)
        self.path = newfile_path
        for key, value in data.items():
            if value[0].ndim <= 2:
                np.savetxt(os.path.join(newfile_path, f'{key}.csv'),
                           np.append(value[0], np.reshape(value[1], (1, -1)), axis=0), fmt='%.15f', delimiter=',')
            elif key == 'monitor 0':
                shape_0 = value[0].shape[0] * value[0].shape[2]
                shape_1 = value[0].shape[1] * value[0].shape[3]
                np.savetxt(os.path.join(newfile_path, f'{key}.csv'),
                           np.reshape(value[0], (shape_0, shape_1)), delimiter=',', fmt='%d')
                with open(os.path.join(newfile_path, f'{key}.csv'), 'a', newline='') as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(value[1])
                    writer.writerow(value[0].shape)
            else:
                raise Exception(f"Unknown stream data shape")
    # def reload_current_csv(self):
    #     if self.path is None:
    #         raise Exception("No csv file is just stored, please call store_csv first")
    #     file_list = os.listdir(self.file)
    #     data = {}
    #     for file_name in file_list:
    #         key = file_name.replace('.csv', '')
    #         value = []
    #         with open(os.path.join(dir_path, file_name), 'r') as file:
    #             # Read the contents of the file
    #             reader = csv.reader(file)
    #             contents = list(reader)
    #         if key == 'monitor 0':
    #             converted = [[float(element) for element in row] for row in contents[:-2]]
    #             value.append(np.array(converted))
    #             value.append(np.array([float(element) for element in contents[-2]]))
    #             dim = [int(element) for element in contents[-1]]
    #             np.reshape(value[0], tuple(dim))
    #         else:
    #             converted = [[float(element) for element in row] for row in contents[:-1]]
    #             value.append(np.array(converted))
    #             value.append(np.array([float(element) for element in contents[-1]]))
    #         data[key] = value
    #     return data

    def reload_csv(self, dir_path):
        # Open the CSV file for reading
        file_list = os.listdir(dir_path)
        data = {}
        for file_name in file_list:
            key = file_name.replace('.csv', '')
            value = []
            with open(os.path.join(dir_path, file_name), 'r') as file:
                # Read the contents of the file
                reader = csv.reader(file)
                contents = list(reader)
            if key == 'monitor 0':
                converted = [[float(element) for element in row] for row in contents[:-2]]
                value.append(np.array(converted))
                value.append(np.array([float(element) for element in contents[-2]]))
                dim = [int(element) for element in contents[-1]]
                np.reshape(value[0], tuple(dim))
            else:
                converted = [[float(element) for element in row] for row in contents[:-1]]
                value.append(np.array(converted))
                value.append(np.array([float(element) for element in contents[-1]]))
            data[key] = value
        return data

