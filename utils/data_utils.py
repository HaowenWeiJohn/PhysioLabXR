import math
import os
from pathlib import Path
from statistics import mode

import cv2
import matplotlib.pyplot as plt
import mne
import numpy as np
from scipy.interpolate import interp1d
from scipy.signal import resample

from utils import nslr_hmm
from utils.sig_proc_utils import notch_filter, baseline_correction, butter_bandpass_filter


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
        out_file = open(self.fn, "ab")
        stream_label_bytes, dtype_bytes, dim_bytes, shape_bytes, data_bytes, ts_bytes = \
            b'', b'', b'', b'', b'', b''
        for stream_label, data_ts_array in buffer.items():
            data_array, ts_array = data_ts_array[0], data_ts_array[1]
            stream_label_bytes = \
                bytes(stream_label[:max_label_len] + "".join(
                    " " for x in range(max_label_len - len(stream_label))), encoding)
            try:
                dtype_str = str(data_array.dtype)
                assert len(dtype_str) < max_dtype_len
            except AssertionError:
                raise Exception('dtype encoding exceeds 8 characters, please contact support')
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
        out_file.close()
        return len(magic + stream_label_bytes + dtype_bytes + dim_bytes + shape_bytes + data_bytes + ts_bytes)

    def stream_in(self, ignore_stream=None, only_stream=None, jitter_removal=True):
        """
        different from LSL XDF importer, this jitter removal assumes no interruption in the data
        :param ignore_stream:
        :param only_stream:
        :param jitter_removal:
        :return:
        """
        total_bytes = float(os.path.getsize(self.fn))  # use floats to avoid scalar type overflow
        buffer = {}
        read_bytes_count = 0.
        with open(self.fn, "rb") as file:
            while True:
                print('Streaming in progress {0}%'.format(str(round(100 * read_bytes_count / total_bytes, 2))), sep=' ',
                      end='\r', flush=True)
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
                print('Removing jitter for streams {0}/{1}'.format(i, len(buffer)), sep=' ',
                      end='\r', flush=True)
                coefs = np.polyfit(list(range(len(ts_array))), ts_array, 1)
                smoothed_ts_array = np.array([i * coefs[0] + coefs[1] for i in range(len(ts_array))])
                buffer[stream_name][1] = smoothed_ts_array

        print("Stream-in completed: {0}".format(self.fn))
        return buffer

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
        output_path = os.path.join(data_root, '{0}_{1}.avi'.format(data_fn.split('.')[0],
                                                                   video_stream_name)) if output_path == '' else output_path

        out = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*'DIVX'), frate, frame_size)

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
                 EEG_stream_preset, lowcut=0.5, highcut=50., notch_band_demoninator=200, EEG_fresample=50,
                 baselining=True, notes='', target_label=4, nontarget_labels=(2, 3, 5, 6),
                 baseline_tmin=-0.5, baseline_tmax=0.1, pupil_channels=['Pupil Left', 'Pupil Right']):
    EEG_num_sample_per_trail = int(EEG_stream_preset['NominalSamplingRate'] * (post_stimulus_time - pre_stimulus_time))
    EEG_num_sample_per_trail_RESAMPLED = int(EEG_fresample * (post_stimulus_time - pre_stimulus_time))
    EEG_num_chan = EEG_stream_preset['GroupChannelsInPlot'][1] - EEG_stream_preset['GroupChannelsInPlot'][0]
    epoched_EEG = np.empty(shape=(0, EEG_num_chan, EEG_num_sample_per_trail))
    biosemi_64_montage = mne.channels.make_standard_montage('biosemi64')
    EEG_chan_names = biosemi_64_montage.ch_names
    events_EEG = np.empty(shape=(0, 3), dtype=int)
    reject = dict(eeg=600.)
    _evoked_target_all_session_EEG = []
    _evoked_nontarget_all_session_EEG = []
    _evoked_trial_starts_all_session_EEG = []

    _evoked_target_all_session_PUPIL = []
    _evoked_nontarget_all_session_PUPIL = []

    target_count = 0
    nontarget_count = 0
    bad_foveate_count_target = 0
    bad_foveate_count_nontarget = 0

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
        stream_EYE = data['Unity.ViveSREyeTracking'][0]
        timestamps_EYE = data['Unity.ViveSREyeTracking'][1]
        array_left_gaze = stream_EYE[4:6, :]

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
        array_EEG = stream_EEG[
                    EEG_stream_preset['GroupChannelsInPlot'][0]:EEG_stream_preset['GroupChannelsInPlot'][1],
                    :]
        array_PUPIL = stream_EYE[0:2]

        # create STIM stream from stream EM ############################################
        array_STIM_for_EEG = create_stim_channel(array_event_label, timestamps_EM, timestamps_EEG)
        array_STIM_for_eye = create_stim_channel(array_event_label, timestamps_EM, timestamps_EYE)

        # concatenate EEG and its STIM channel
        array_EEG = np.concatenate([array_EEG, array_STIM_for_EEG], axis=0)
        array_PUPIL = np.concatenate([array_PUPIL, array_STIM_for_eye], axis=0)
        # not worrying about the timeoffset in mne data structure as we use our own timestamps
        array_EEG = mne.io.RawArray(array_EEG, mne.create_info(EEG_chan_names  + ['stim'], EEG_stream_preset['NominalSamplingRate'],
                                                               ch_types=['eeg'] * len(EEG_chan_names) + ['stim']))
        array_PUPIL = mne.io.RawArray(array_PUPIL, mne.create_info(pupil_channels + ['stim'], 70,
                                                               ch_types=['misc', 'misc'] + ['stim']))

        array_EEG.set_montage(biosemi_64_montage)
        array_EEG, _ = mne.set_eeg_reference(array_EEG, 'average',
                                             projection=False)  # re-reference using average as the reference

        array_EEG = array_EEG.filter(l_freq=lowcut, h_freq=highcut)  # bandpass filter
        array_EEG = array_EEG.notch_filter(freqs=np.arange(60, 241, 60), filter_length='auto')
        array_PUPIL = array_PUPIL.filter(picks=pupil_channels, l_freq=None, h_freq=20.)
        evoked_foveate_dict = {}
        evoked_GAZE_dict = {}

        for tl in target_labels:
            array_target_ONSET_EM = np.logical_and(array_event_label == tl,
                                                   np.concatenate([np.array([0]), np.diff(array_event_label)]) != 0)
            print('Number of trials is {0} for label {1}'.format(np.count_nonzero(array_target_ONSET_EM), tl))
            target_PRE_ONSET_EM_timestamps = timestamps_EM[array_target_ONSET_EM] + pre_stimulus_time
            target_ONSET_EM_timestamps = timestamps_EM[array_target_ONSET_EM]
            target_POST_ONSET_EM_timestamps = timestamps_EM[array_target_ONSET_EM] + post_stimulus_time
            target_ONSET_EM_indices = np.argwhere(array_target_ONSET_EM)[:, 0]

            array_target_PRE_ONSET_EM_indices = np.array(
                [(np.abs(timestamps_EM - x)).argmin() for x in target_PRE_ONSET_EM_timestamps])
            array_target_POST_ONSET_EM_indices = np.array(
                [(np.abs(timestamps_EM - x)).argmin() for x in target_POST_ONSET_EM_timestamps])

            # find the nearest timestamp index in eeg #####################################################
            target_PRE_ONSET_EEG_indices = np.array(
                [(np.abs(timestamps_EEG - x)).argmin() for x in target_PRE_ONSET_EM_timestamps])
            target_ONSET_EEG_indices = np.array(
                [(np.abs(timestamps_EEG - x)).argmin() for x in target_ONSET_EM_timestamps])
            target_POST_ONSET_EEG_indices = np.array(
                [(np.abs(timestamps_EEG - x)).argmin() for x in target_POST_ONSET_EM_timestamps])
            target_ONSET_EEG_timestamps = timestamps_EEG[target_ONSET_EEG_indices]
            print('EM-EEG target onset timestamp discrepency: mean {0}, std {1}'.format(
                np.mean(target_ONSET_EM_timestamps - target_ONSET_EEG_timestamps),
                np.std(target_ONSET_EM_timestamps - target_ONSET_EEG_timestamps)))

            # epoch eeg data #############################################
            # modify pre and post indices for possible remaining jitter

            array_prepost_target_onset_EM_indices = [modify_indice_to_cover(pre_onset_i, post_onset_i, EEG_num_sample_per_trail)
                                               for
                                               pre_onset_i, post_onset_i in
                                               zip(target_PRE_ONSET_EEG_indices,
                                                   target_POST_ONSET_EEG_indices)]

            # manually construct event array based on https://mne.tools/stable/generated/mne.find_events.html#mne.find_events  ####################################
            # ems = np.ones(shape=target_ONSET_EEG_indices.shape) * tl
            # new_events = np.array(
            #     [target_ONSET_EEG_indices, array_event_label[target_ONSET_EM_indices - 1], ems],
            #     dtype=int).T
            # events_EEG = np.concatenate([events_EEG, new_events], axis=0)

            # extract the foveate array #######################################################################################
            stream_EMFoveate = stream_EM[(tl-2) * 2 + 1, :]

            # evoked_target_foveate_list = [stream_EMFoveate[pre_onset_i:post_onset_i] for pre_onset_i, post_onset_i in zip(array_target_PRE_ONSET_EM_indices, array_target_POST_ONSET_EM_indices) ]
            # if tl not in evoked_foveate_dict.keys():
            #     evoked_foveate_dict[tl] = evoked_target_foveate_list
            # else:
            #     evoked_foveate_dict[tl] += evoked_target_foveate_list

            # extract another eeg event array based on foveate peak #################################
            FOVEATE_good_threshold = math.cos(18) ########################
            target_FPEAK_EM_indices = np.array([pre_onset_i + np.argmax(stream_EMFoveate[pre_onset_i:post_onset_i])
                                                for pre_onset_i, post_onset_i in zip(array_target_PRE_ONSET_EM_indices, array_target_POST_ONSET_EM_indices) if np.max(stream_EMFoveate[pre_onset_i:post_onset_i]) >= FOVEATE_good_threshold])
            if tl in nontarget_labels:
                bad_foveate_count_nontarget += len(array_target_PRE_ONSET_EM_indices) - len(target_FPEAK_EM_indices)
            else:
                bad_foveate_count_target += len(array_target_PRE_ONSET_EM_indices) - len(target_FPEAK_EM_indices)

            target_FPEAK_EM_timestamps = timestamps_EM[[x for x in target_FPEAK_EM_indices if x < len(timestamps_EM)]]  # in case the data stream shuts down before the post stimuli time is reached
            target_PRE_FPEAK_EM_timestamps = target_FPEAK_EM_timestamps + pre_stimulus_time
            target_POST_FPEAK_EM_timestamps = target_FPEAK_EM_timestamps + post_stimulus_time

            target_PRE_FPEAK_EM_indices = np.array(
                [(np.abs(timestamps_EM - x)).argmin() for x in target_PRE_FPEAK_EM_timestamps])
            target_POST_FPEAK_EM_indices = np.array(
                [(np.abs(timestamps_EM - x)).argmin() for x in target_POST_FPEAK_EM_timestamps])

            evoked_target_foveate_list = [stream_EMFoveate[pre_onset_i:post_onset_i] for pre_onset_i, post_onset_i in zip(target_PRE_FPEAK_EM_indices, target_POST_FPEAK_EM_indices) ]
            if tl not in evoked_foveate_dict.keys():
                evoked_foveate_dict[tl] = evoked_target_foveate_list
            else:
                evoked_foveate_dict[tl] += evoked_target_foveate_list

            # find the nearest timestamp index in eeg based on Foveate Peak #####################################################
            target_PRE_FPEAK_EEG_indices = np.array(
                [(np.abs(timestamps_EEG - x)).argmin() for x in target_PRE_FPEAK_EM_timestamps])
            target_FPEAK_EEG_indices = np.array(
                [(np.abs(timestamps_EEG - x)).argmin() for x in target_FPEAK_EM_timestamps])
            target_POST_FPEAK_EEG_indices = np.array(
                [(np.abs(timestamps_EEG - x)).argmin() for x in target_POST_FPEAK_EM_timestamps])
            target_FPEAK_EEG_timestamps = timestamps_EEG[target_FPEAK_EEG_indices]
            print('EM-EEG target Foveate Peak timestamp discrepency: mean {0}, std {1}'.format(
                np.mean(target_FPEAK_EM_timestamps - target_FPEAK_EEG_timestamps),
                np.std(target_FPEAK_EM_timestamps - target_FPEAK_EEG_timestamps)))

            ems = np.ones(shape=target_FPEAK_EEG_indices.shape) * tl
            new_events = np.array(
                [target_FPEAK_EEG_indices, array_event_label[target_FPEAK_EM_indices - 1], ems],
                dtype=int).T
            events_EEG = np.concatenate([events_EEG, new_events], axis=0)

            # classify eye movement
            target_PRE_ONSET_EYE_indices = np.array(
                [(np.abs(timestamps_EYE - x)).argmin() for x in target_PRE_ONSET_EM_timestamps])
            target_ONSET_EYE_indices = np.array(
                [(np.abs(timestamps_EYE - x)).argmin() for x in target_ONSET_EM_timestamps])
            target_POST_ONSET_EYE_indices = np.array(
                [(np.abs(timestamps_EYE - x)).argmin() for x in target_POST_ONSET_EM_timestamps])
            target_ONSET_EYE_timestamps = timestamps_EYE[target_ONSET_EYE_indices]
            print('EM-EEG target onset timestamp discrepency: mean {0}, std {1}'.format(
                np.mean(target_ONSET_EM_timestamps - target_ONSET_EEG_timestamps),
                np.std(target_ONSET_EM_timestamps - target_ONSET_EEG_timestamps)))
            evoked_target_GAZE_list = [array_left_gaze[:, pre_onset_i:post_onset_i] for pre_onset_i, post_onset_i in zip(target_PRE_ONSET_EYE_indices, target_POST_ONSET_EYE_indices) ]
            if tl not in evoked_GAZE_dict.keys():
                evoked_GAZE_dict[tl] = evoked_target_GAZE_list
            else:
                evoked_GAZE_dict[tl] += evoked_target_GAZE_list

        events_EEG = np.sort(events_EEG, axis=0)
        target_count += np.count_nonzero(events_EEG[:, 2] == target_label)
        nontarget_count += np.count_nonzero(np.isin(events_EEG[:, 2], nontarget_labels))

        ##################################################################
        epochs_params = dict(events=events_EEG, event_id=target_label, tmin=pre_stimulus_time, tmax=post_stimulus_time,
                             baseline=(baseline_tmin, baseline_tmax), reject=reject)
        evoked_target_EEG = mne.Epochs(raw=array_EEG, **epochs_params)
        epochs_params = dict(events=events_EEG, event_id=list(nontarget_labels), tmin=pre_stimulus_time, tmax=post_stimulus_time,
                             baseline=(baseline_tmin, baseline_tmax), reject=reject)
        evoked_nontarget_EEG = mne.Epochs(raw=array_EEG, **epochs_params)
        print('Total number of trials for label {0} is {1}'.format(str(target_labels), len(epoched_EEG)))

        # find the base line period ##########################################
        mne_events_EEG = mne.find_events(array_EEG, ['stim'])
        epochs_params = dict(events=mne_events_EEG, event_id=1, tmin=-0.2, tmax=0., baseline=None, reject=reject)
        evoked_trial_starts = mne.Epochs(raw=array_EEG, **epochs_params)

        _evoked_trial_starts_all_session_EEG.append(evoked_trial_starts)
        _evoked_target_all_session_EEG.append(evoked_target_EEG)
        _evoked_nontarget_all_session_EEG.append(evoked_nontarget_EEG)

        # Pupil data #####################################################
        mne_events_PUPIL = mne.find_events(array_PUPIL, ['stim'])
        evoked_target_PUPIL = mne.Epochs(raw=array_PUPIL, **dict(events=mne_events_PUPIL, event_id=target_label, tmin=-.5, tmax=2.,  baseline=(-0.1, 0.1)))
        evoked_nontarget_PUPIL = mne.Epochs(raw=array_PUPIL, **dict(events=mne_events_PUPIL, event_id=list(nontarget_labels), tmin=-.5, tmax=2.,  baseline=(-0.1, 0.1)))
        _evoked_target_all_session_PUPIL.append(evoked_target_PUPIL)
        _evoked_nontarget_all_session_PUPIL.append(evoked_nontarget_PUPIL)

    print('{0}/{1} FOVEATE was dropped for Target.-----------------------'.format(bad_foveate_count_target, target_count))
    print('{0}/{1} FOVEATE was dropped for NonTarget.--------------------'.format(bad_foveate_count_nontarget, nontarget_count))

    # manual baseline correction
    # baseline_data = np.average(mne.concatenate_epochs(_evoked_trial_starts_all_session).average().data, axis=-1)

    ######################################################################################################################
    evoked_target_all_session_EEG = mne.concatenate_epochs(_evoked_target_all_session_EEG).resample(sfreq=EEG_fresample)
    # evoked_target_all_session.data = np.array([ts - ch_b for ts, ch_b in zip(evoked_target_all_session.data, baseline_data)])
    print('{0}/{1} was dropped for Target.'.format(
        target_count - mne.concatenate_epochs(_evoked_target_all_session_EEG).get_data().shape[0], target_count))

    print('---------------------loading nonTargets')
    evoked_nontarget_all_session_EEG = mne.concatenate_epochs(_evoked_nontarget_all_session_EEG).resample(sfreq=EEG_fresample)
    # evoked_nontarget_all_session.data = np.array([ts - ch_b for ts, ch_b in zip(evoked_nontarget_all_session.data, baseline_data)])
    print('{0}/{1} was dropped for NonTarget.'.format(
        nontarget_count - mne.concatenate_epochs(_evoked_nontarget_all_session_EEG).get_data().shape[0], nontarget_count))

    evoked_all_EEG = np.concatenate([evoked_target_all_session_EEG.average().data, evoked_nontarget_all_session_EEG.average().data])
    vmax_EEG = np.max(evoked_all_EEG)
    vmin_EEG = np.min(evoked_all_EEG)

    ######################################################################################################################
    time_vector_pupil = np.linspace(-.5, 2., 50)
    evoked_target_all_session_PUPIL = mne.concatenate_epochs(_evoked_target_all_session_PUPIL).resample(sfreq=20.)
    evoked_target_all_session_PUPIL = evoked_target_all_session_PUPIL.get_data(picks=pupil_channels)
    evoked_target_all_session_PUPIL = np.average(evoked_target_all_session_PUPIL, axis=1)  # average left and right

    evoked_nontarget_all_session_PUPIL = mne.concatenate_epochs(_evoked_nontarget_all_session_PUPIL).resample(sfreq=20.)
    evoked_nontarget_all_session_PUPIL = evoked_nontarget_all_session_PUPIL.get_data(picks=pupil_channels)
    evoked_nontarget_all_session_PUPIL = np.average(evoked_nontarget_all_session_PUPIL, axis=1)

    title = notes + ' Targets; Baseline [{0}, {1}]'.format(-0.1, 0.1)

    plt.plot(time_vector_pupil, np.average(evoked_target_all_session_PUPIL, axis=0), c='r', label='Targets')
    y2 = np.average(evoked_target_all_session_PUPIL, axis=0) + np.std(evoked_target_all_session_PUPIL, axis=0)
    y1 = np.average(evoked_target_all_session_PUPIL, axis=0) - np.std(evoked_target_all_session_PUPIL, axis=0)
    plt.fill_between(time_vector_pupil, y2, y1, where=y2 >= y1, facecolor='r', interpolate=True, alpha=0.5)

    plt.plot(time_vector_pupil, np.average(evoked_nontarget_all_session_PUPIL, axis=0), c='b', label='Non-targets')
    y2 = np.average(evoked_nontarget_all_session_PUPIL, axis=0) + np.std(evoked_nontarget_all_session_PUPIL, axis=0)
    y1 = np.average(evoked_nontarget_all_session_PUPIL, axis=0) - np.std(evoked_nontarget_all_session_PUPIL, axis=0)
    plt.fill_between(time_vector_pupil, y2, y1, where=y2 >= y1, facecolor='b', interpolate=True, alpha=0.5)

    plt.title(title)
    plt.xlabel('Time (sec)')
    plt.ylabel('Baselined Pupil Diameter (mm)')
    plt.legend()
    plt.show()


    evoked_all_PUPIL = np.concatenate([evoked_target_all_session_PUPIL.data, evoked_nontarget_all_session_PUPIL.data])
    vmax_PUPIL = np.max(evoked_all_PUPIL)
    vmin_PUPIL= np.min(evoked_all_PUPIL)

    # plot pupil #################################################################
    title = notes + ' Targets; Baseline [{0}, {1}]'.format(-0.1, 0.1)






    title = notes + ' Targets'
    # evoked_target_all_session.plot_topomap(times=[0.3], size=3., title=title, time_unit='s', scalings=dict(eeg=1.), vmax=vmax, vmin=vmin)
    get_animated_topomap(evoked_target_all_session_EEG, pre_stimulus_time, post_stimulus_time, vmax_EEG, vmin_EEG, title)  # create gif
    # evoked_target_all_session.plot(gfp=True, spatial_colors=True, ylim=dict(eeg=[-40, 20]), titles=dict(eeg=title),
    #                                scalings=dict(eeg=1.))

    title = notes + ' Non-targets'
    # evoked_nontarget_all_session.plot_topomap(times=[0.3], size=3., title=title, time_unit='s', scalings=dict(eeg=1.), vmax=vmax, vmin=vmin)
    get_animated_topomap(evoked_nontarget_all_session_EEG, pre_stimulus_time, post_stimulus_time, vmax_EEG, vmin_EEG, title)  # create gif
    # evoked_nontarget_all_session.plot(gfp=True, spatial_colors=True, ylim=dict(eeg=[-40, 20]), titles=dict(eeg=title),
    #                                   scalings=dict(eeg=1.))



def get_animated_topomap(evoked, preT, postT, vmax, vmin, title, fps=30):
    num_frame = int((postT - preT) * fps)
    interval = 1 / fps
    fig_array_list = []

    for i in range(num_frame):
        time = preT + i * interval
        fig = evoked.plot_topomap(times=[time], size=3., title=title, time_unit='s', scalings=dict(eeg=1.), vmax=vmax,
                                  vmin=vmin)
        fig_array = np.fromstring(fig.canvas.tostring_rgb(), dtype=np.uint8, sep='')
        fig_array = fig_array.reshape(fig.canvas.get_width_height()[::-1] + (3,))
        fig_array_list.append(fig_array)
    import imageio
    imageio.mimsave('{0}_animated.gif'.format(title), fig_array_list, fps=5)  # slow down plotting


def get_channel_data(evoked_target_all_session, evoked_nontarget_all_session, channel_names, vmax, vmin, preT, postT):
    picks = ['Fz', 'Cz', 'POz', 'Oz']
    target_midline = evoked_target_all_session.pick_channels(picks).data
    nontarget_midline = evoked_nontarget_all_session.pick_channels(picks).data
    time_vector = np.linspace(preT, postT, target_midline.shape[-1])
    for i, (target_chan_data, nontarget_chan_data) in enumerate(zip(target_midline, nontarget_midline)):
        plt.plot(time_vector, target_chan_data, c='r',
                 label='{0} Target '.format(picks[i]) + r'$N_{avg}$=' + str(evoked_target_all_session.nave))
        plt.plot(time_vector, nontarget_chan_data, c='b',
                 label='{0} Non-target '.format(picks[i]) + r'$N_{avg}$=' + str(evoked_nontarget_all_session.nave))
        plt.ylim([vmin, vmax])
        plt.legend()
        plt.xlabel('Time (sec)')
        plt.ylabel('\u03bcV')
        plt.title('Interleaved Sessions')
        # plt.title('All Sessions (interleave + block) ')
        plt.show()


def plot_eeg_with_fustum_foveate_trace(evoked_target_all_session_EEG, evoked_nontarget_all_session_EEG, evoked_target_all_session_PUPIL, evoked_nontarget_all_session_PUPIL, pre_stimulus_time, post_stimulus_time,
                                        EEG_fresample, _evoked_target_all_session_EEG, _evoked_nontarget_all_session_EEG,
                                       evoked_foveate_dict, evoked_GAZE_dict, target_label, nontarget_labels, baseline_tmin, baseline_tmax, pupil_channels, notes):
    timesteps_FOVEATE = mode([len(x) for x in evoked_foveate_dict[target_label]])
    timesteps_GAZE = mode([x.shape[-1] for x in evoked_GAZE_dict[target_label]])
    timesteps_EEG = evoked_target_all_session_EEG.average().data.shape[-1]

    time_vec_EEG = np.linspace(pre_stimulus_time, post_stimulus_time, num=timesteps_EEG)
    time_vec_GAZE = np.linspace(pre_stimulus_time, post_stimulus_time, num=timesteps_GAZE)

    # foveate data
    time_vec_FOVEATE = np.linspace(pre_stimulus_time, post_stimulus_time, num=timesteps_FOVEATE)
    evoked_target_foveate_list = [[x if x != 0 else np.NAN for x in seq] for seq in evoked_foveate_dict[target_label] if len(seq) == timesteps_FOVEATE]
    evoked_nontarget_foveate_list = []
    for nontarget_l in nontarget_labels:
        evoked_nontarget_foveate_list += [[x if x != 0 else np.NAN for x in seq] for seq in evoked_foveate_dict[nontarget_l] if len(seq) == timesteps_FOVEATE]
    evoked_target_foveate_array = np.array(evoked_target_foveate_list)
    evoked_nontarget_foveate_array = np.array(evoked_nontarget_foveate_list)

    # gaze data  #################################################
    COLORS = {
        nslr_hmm.FIXATION: 'blue',
        nslr_hmm.SACCADE: 'black',
        nslr_hmm.SMOOTH_PURSUIT: 'green',
        nslr_hmm.PSO: 'yellow',
    }
    eye = np.copy(evoked_GAZE_dict[4][3])
    # eye = np.array([interp_zero(x) for x in eye])
    eye = eye.transpose()
    eye = eye * 10.
    plt.plot(eye[:, 1])
    plt.plot(eye[:, 0])
    plt.show()

    sample_class, segmentation, seg_class = nslr_hmm.classify_gaze(time_vec_GAZE, eye)
    plt.plot(time_vec_GAZE, eye[:, 0], '.')
    for i, seg in enumerate(segmentation.segments):
        cls = seg_class[i]
        plt.plot(seg.t, np.array(seg.x)[:, 0], color=COLORS[cls])

    plt.show()

    # visualization
    color = 'tab:red'
    # picks = ['Fpz', 'AFz', 'Fz', 'FCz', 'Cz', 'CPz', 'Pz', 'POz', 'Oz']
    picks = ['Fpz', 'Fz',  'Cz', 'Pz', 'Oz']

    # for targets #########################################################################
    title = notes + ' Targets; Baseline [{0}, {1}]'.format(baseline_tmin, baseline_tmax)
    fig = evoked_target_all_session_EEG.average().plot(gfp=True, spatial_colors=True, ylim=dict(eeg=[-30, 20]),
                                             titles=dict(eeg=title), scalings=dict(eeg=1.), show=False)
    fig.set_size_inches(8, 3)
    ax2 = fig.axes[0].twinx()
    ax2.set_ylabel('Foveate value', color=color)
    y1 = np.nanmean(evoked_target_foveate_array, axis=0) - np.nanstd(evoked_target_foveate_array, axis=0)
    y2 = np.nanmean(evoked_target_foveate_array, axis=0) + np.nanstd(evoked_target_foveate_array, axis=0)
    ax2.fill_between(time_vec_FOVEATE, y2, y1, where=y2 >= y1, facecolor=color, interpolate=True, alpha=0.5)
    ax2.plot(time_vec_FOVEATE, np.nanmean(evoked_target_foveate_array, axis=0), c=color)
    ax2.tick_params(axis='y', labelcolor=color)
    ax2.set_ylim(-1., 1.)
    fig.tight_layout()
    plt.show()


    # for nontargets #########################################################################
    title = notes + ' Non-targets; BL [{0}, {1}]'.format(baseline_tmin, baseline_tmax)
    fig = evoked_nontarget_all_session_EEG.average().plot(gfp=True, spatial_colors=True, ylim=dict(eeg=[-30, 20]),
                                                titles=dict(eeg=title), scalings=dict(eeg=1.), show=False)
    fig.set_size_inches(8, 3)
    ax2 = fig.axes[0].twinx()
    ax2.set_ylabel('Foveate value', color=color)
    y1 = np.nanmean(evoked_nontarget_foveate_array, axis=0) - np.nanstd(evoked_nontarget_foveate_array, axis=0)
    y2 = np.nanmean(evoked_nontarget_foveate_array, axis=0) + np.nanstd(evoked_nontarget_foveate_array, axis=0)
    ax2.fill_between(time_vec_FOVEATE, y2, y1, where=y2 >= y1, facecolor=color, interpolate=True, alpha=0.5)
    ax2.plot(time_vec_FOVEATE, np.nanmean(evoked_nontarget_foveate_array, axis=0), c=color)
    ax2.tick_params(axis='y', labelcolor=color)
    ax2.set_ylim(-1., 1.)
    fig.tight_layout()
    plt.show()

    # plot for different channels #########
    for ch in picks:
        title = notes + ' Targets; Baseline [{0}, {1}]; Channel {2}'.format(baseline_tmin, baseline_tmax, ch)
        evoked_target_all_session_EEG = mne.concatenate_epochs(_evoked_target_all_session_EEG).resample(
            sfreq=EEG_fresample)
        evoked_nontarget_all_session_EEG = mne.concatenate_epochs(_evoked_nontarget_all_session_EEG).resample(
            sfreq=EEG_fresample)

        fig, ax = plt.subplots()

        y = evoked_target_all_session_EEG.pick_channels([ch]).get_data().reshape((-1, len(time_vec_EEG)))
        y1 = np.mean(y, axis=0) + np.std(y, axis=0)
        y2 = np.mean(y, axis=0) - np.std(y, axis=0)
        ax.plot(time_vec_EEG, np.mean(y, axis=0), c='r', label='Target')
        ax.fill_between(time_vec_EEG, y1, y2, where=y2 <= y1, facecolor='r', interpolate=True, alpha=0.5)

        y = evoked_nontarget_all_session_EEG.pick_channels([ch]).get_data().reshape((-1, len(time_vec_EEG)))
        y1 = np.mean(y, axis=0) + np.std(y, axis=0)
        y2 = np.mean(y, axis=0) - np.std(y, axis=0)
        ax.plot(time_vec_EEG, np.mean(y, axis=0), c='b', label='Non-target')
        ax.fill_between(time_vec_EEG, y1, y2, where=y2 <= y1, facecolor='b', interpolate=True, alpha=0.5)

        ax.set_title(title)
        ax.set_xlabel('Time (sec)')
        ax.set_ylabel('\u03BCV')
        plt.legend()
        # fig.set_size_inches(8, 3)
        plt.show()


def interp_zero(y):
    x = np.arange(len(y))
    idx = np.nonzero(y)
    interp = interp1d(x[idx],y[idx], fill_value='extrapolate')

    return interp(x)


# title = notes + ' NonTargets (No value = eye closed)'
# fig = evoked_nontarget_all_session.plot(gfp=True, spatial_colors=True, ylim=dict(eeg=[-40, 20]),
#                                      titles=dict(eeg=title), scalings=dict(eeg=1.), show=False)
# fig.clear()
# ax2 = fig.subplots()
# ax2.set_ylabel('Foveate value')
# [ax2.plot(time_vec_FOVEATE, x) for x in evoked_nontarget_foveate_array]
# ax2.tick_params(axis='y')
# ax2.set_ylim(-1., 1.)
# ax2.set_title(title)
# plt.show()

def create_stim_channel(array_event_label, timestamps_EM, timestamps_sensor):
    trial_num = 24
    item_event_labels = [2,3,4,5,6]
    target_label = 4

    array_event_label_altered = np.zeros(len(array_event_label))

    trial_start_idx = [i for i, x in enumerate(array_event_label) if x == 1 and np.all(array_event_label[i-50:i] == 0)]
    array_event_label_altered[trial_start_idx] = 1
    # assert len(trial_start_idx) == trial_num

    for il in item_event_labels:
        item_ONSET_idx = np.argwhere(np.logical_and(array_event_label == il, np.concatenate([np.array([0]), np.diff(array_event_label)]) != 0))[:, 0]
        # assert len(item_ONSET_idx) == trial_num
        array_event_label_altered[item_ONSET_idx] = il

    timestamps_EM_events = timestamps_EM[np.argwhere(array_event_label_altered)]  # the EM timestamps at when something happened
    # assert len(timestamps_EM_events) == trial_num * (len(item_event_labels) + 1)

    # find the corresponding EEG timestamps
    target_ONSET_EEG_indices = np.array(
        [(np.abs(timestamps_sensor - x)).argmin() for x in timestamps_EM_events])
    target_ONSET_EEG_timestamps = timestamps_sensor[target_ONSET_EEG_indices]
    print('EM target onset timestamp discrepency: mean {0}, std {1}'.format(
        np.mean(timestamps_EM_events - target_ONSET_EEG_timestamps),
        np.std(timestamps_EM_events - target_ONSET_EEG_timestamps)))

    array_eeg_stim = np.zeros(len(timestamps_sensor))
    array_eeg_stim[target_ONSET_EEG_indices] = array_event_label_altered[np.argwhere(array_event_label_altered)[:, 0]]

    return np.expand_dims(array_eeg_stim, axis=0)
    # sanity checks

    plt.plot(timestamps_EM[1400:1700], array_event_label[1400:1700])
    plt.show()

    # plt.plot(array_event_label[1400:1700])
    # plt.plot(array_event_label_altered[1400:1700])
    # plt.show()
    #
    # plt.plot(array_event_label[1000:1800])
    # plt.plot(array_event_label_altered[1000:1800])
    # plt.show()
    #
    # plt.plot(array_event_label[1000:8000])
    # plt.plot(array_event_label_altered[1000:8000])
    # plt.show()
    #
    # plt.plot(array_eeg_stim[74600:74900])
    # plt.show()
    #
    # plt.plot(array_eeg_stim[74600:74600 + 2048 * 10])
    # plt.show()

# def project_gaze_vector():
