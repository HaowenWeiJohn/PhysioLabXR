import numpy as np
import json
from utils.data_utils import RNStream, integer_one_hot
from sklearn.preprocessing import OneHotEncoder


exp_info_dict = json.load(open('../IndexPen_utils/IndexPenExp.json'))

reshape_dict = {
    'TImmWave_6843AOP': [(8, 16, 1), (8, 64, 1)]
}

sample_num = 120

# get useful timestamps
DataStreamName = 'TImmWave_6843AOP'

ExpID = exp_info_dict['ExpID']
ExpLSLStreamName = exp_info_dict['ExpLSLStreamName']
ExpStartMarker = exp_info_dict['ExpStartMarker']
ExpEndMarker = exp_info_dict['ExpEndMarker']
ExpLabelMarker = exp_info_dict['ExpLabelMarker']
ExpInterruptMarker = exp_info_dict['ExpInterruptMarker']
ExpErrorMarker = exp_info_dict['ExpErrorMarker']

# one-hot encoder
all_categories = list(ExpLabelMarker.values())
encoder = OneHotEncoder(categories='auto')
encoder.fit(np.reshape(all_categories, (-1, 1)))


X_dict = dict()
Y = []


rs_stream = RNStream('C:/Recordings/John_test_A-E/05_31_2021_15_53_21-Exp_IndexPen_test-Sbj_HW-Ssn_0.dats')



data = rs_stream.stream_in(reshape_stream_dict=reshape_dict)
data['TImmWave_6843AOP'][0][0] = np.moveaxis(data['TImmWave_6843AOP'][0][0], -1, 0)
data['TImmWave_6843AOP'][0][1] = np.moveaxis(data['TImmWave_6843AOP'][0][1], -1, 0)

# extract experiment session

# extract 120 frames after each label event marker

index_buffer = []
label_buffer = []

event_markers = data[ExpLSLStreamName][0][0]
session_start_marker_indexes = np.where(event_markers == 100)[0]

for start_marker_index in session_start_marker_indexes:
    # forward track the event marker
    session_index_buffer = []
    session_label_buffer = []
    for index in range(start_marker_index + 1, len(event_markers)):
        # stop the forward tracking and go for the next session if interrupt Marker found
        if event_markers[index] == ExpInterruptMarker:
            break
        elif event_markers[index] == ExpID:
            break
        elif event_markers[index] == ExpEndMarker:
            # only attach the event marker with regular exit
            index_buffer.extend(session_index_buffer)
            label_buffer.extend(session_label_buffer)
            break

        # remove last element from the list
        if event_markers[index] == ExpErrorMarker and len(session_index_buffer) != 0:
            del session_index_buffer[-1]
            del session_label_buffer[-1]
            continue

        session_index_buffer.append(index)
        session_label_buffer.append(event_markers[index])

# get all useful timestamps using index list
label_start_time_stamps = data[ExpLSLStreamName][1][index_buffer]
# loop through each label time stamp and find starting index for each label

label_start_time_stamp_indexes = []
for time_stamp in label_start_time_stamps:
    label_start_time_stamp_indexes.append(np.where(data[DataStreamName][1] > time_stamp)[0][0])

q = data[DataStreamName][0]
# extract n frames for each stream after each time stamp

for ts_index in label_start_time_stamp_indexes:
    for channel in data[DataStreamName][0]:
        if channel in X_dict:
            append_data = np.array(data[DataStreamName][0][channel][ts_index:ts_index + sample_num])
            X_dict[channel] = np.concatenate([X_dict[channel],
                                              np.expand_dims(np.array(data[DataStreamName][0][channel]
                                                                      [ts_index:ts_index + sample_num]), axis=0)
                                              ])
        else:
            X_dict[channel] = np.expand_dims(
                np.array(data[DataStreamName][0][channel][ts_index:ts_index + sample_num]), axis=0)

Y.extend(label_buffer)

Y = encoder.transform(np.reshape(Y, (-1, 1))).toarray()
