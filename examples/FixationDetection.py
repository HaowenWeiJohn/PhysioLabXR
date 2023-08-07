import cv2
import numpy as np

from rena.scripting.RenaScript import RenaScript
from rena.scripting.physio.epochs import get_event_locked_data, buffer_event_locked_data, get_baselined_event_locked_data
from rena.scripting.physio.eyetracking import gap_fill, fixation_detection_idt
from rena.scripting.physio.utils import time_to_index
from rena.utils.buffers import DataBuffer


class FixationDetection(RenaScript):
    def __init__(self, *args, **kwargs):
        """
        Please do not edit this function
        """
        super().__init__(*args, **kwargs)

    # Start will be called once when the run button is hit.
    def init(self):
        self.max_gap_time = 0.075  # the maximum time for gap to be considered a glitch that will be filled

        self.gaze_channels = ['x', 'y', 'z', 'status']
        self.gaze_status = {'valid': 2, 'invalid': 0}

        self.gaze_stream_name = 'Example-Eyetracking'

        self.fixation_timestamp_head = 0
        self.video_stream_name = 'Example-Video'
        self.video_shape = (400, 400, 3)

        self.frame_gaze_pixel_stream_name = 'Example-Video-Gaze-Pixel'

        self.processed_gaze_buffer = DataBuffer()

        self.fixation_circle_color = (255, 0, 0)
        self.gaze_circle_color = (0, 0, 255)


    # loop is called <Run Frequency> times per second
    def loop(self):
        # gap filling
        # if the last sample is valid, we go back and see if there's any gap needs to be filled
        # once the gaps are filled we send the gap-filled data and clear 'em from the buffer

        if self.gaze_stream_name in self.inputs.keys():
            gaze_status = self.inputs[self.gaze_stream_name][0][self.gaze_channels.index('status')]
            gaze_timestamps = self.inputs[self.gaze_stream_name][1]
            gaze_xyz = self.inputs[self.gaze_stream_name][0][:3]

            # if gaze_status[0] == self.gaze_status['invalid']:
            #     start_invalid_end_index = np.where(gaze_status != self.gaze_status['invalid'])[0][0]
            #     starting_invalid_duration = gaze_timestamps[start_invalid_end_index] - gaze_timestamps[0]
            if gaze_status[-1] == self.gaze_status['valid']:  # and starting_invalid_duration > self.max_gap_time:  # if the sequence starts out invalid, we must wait until the end of the invalid
                gap_filled_xyz = gap_fill(gaze_xyz, gaze_status, self.gaze_status['valid'], gaze_timestamps, max_gap_time=self.max_gap_time, verbose=False)
                self.processed_gaze_buffer.update_buffer({'stream_name': 'gap_filled_xyz', 'frames': gap_filled_xyz, 'timestamps': gaze_timestamps})  # add the gap filled data to the buffer, so we can use it for fixation detection
                self.outputs['gap_filled_xyz'] = gap_filled_xyz  # send the gap filled data to the output so we can see it in the viewer
                self.inputs.clear_stream_buffer(self.gaze_stream_name)  # clear the gaze stream, so we don't process the same data again, the fixation detection will act on the gap filled data

            # up to the point of the last gap filled index, we detect fixation. The idt window ends at the gap filled index
            fixations, last_window_start = fixation_detection_idt(*self.processed_gaze_buffer['gap_filled_xyz'], window_size=self.params['idt_window_size'], dispersion_threshold_degree=self.params['dispersion_threshold_degree'], return_last_window_start=True)
            self.processed_gaze_buffer.clear_stream_up_to('gap_filled_xyz', last_window_start)
            self.processed_gaze_buffer.update_buffer({'stream_name': 'fixations', 'frames': fixations[0:1], 'timestamps': fixations[1]})  # add the gap filled data to the buffer, so we can use it for fixation detection
            self.outputs['fixations'] = fixations[0:1]
            self.fixation_timestamp_head = self.processed_gaze_buffer['gap_filled_xyz'][1][last_window_start]  # update the gaze timestamp head, so we can release video frames up to this timestamp
        this_frame_timestamp = 0
        # release video frames up to the processed gaze timestamp, but we only release one video frame per loop
        while self.video_stream_name in self.inputs.keys() and len(self.inputs[self.video_stream_name][1]) > 0 and self.inputs[self.video_stream_name][1][0] < self.fixation_timestamp_head:
        # if self.video_stream_name in self.inputs.keys():
            video_timestamps = self.inputs[self.video_stream_name][1]
            video_frames = self.inputs[self.video_stream_name][0]
            frame_pixels = self.inputs[self.frame_gaze_pixel_stream_name][0]  # find the frame pixel corresponding to the video timestamp
            frame_pixel_timestamps = self.inputs[self.frame_gaze_pixel_stream_name][1]

            if video_timestamps[0] < self.fixation_timestamp_head:
                this_frame = video_frames[:, 0].reshape(self.video_shape).copy()  # take the first frame in the buffer, make a copy so the data is contiguous
                this_frame_timestamp = self.inputs[self.video_stream_name][1][0]
                this_frame_pixel = frame_pixels[:, frame_pixel_timestamps == this_frame_timestamp]

                fixation_index = time_to_index(self.processed_gaze_buffer['fixations'][1], this_frame_timestamp)  # find the closest fixation to the current video frame
                is_fixation = self.processed_gaze_buffer['fixations'][0][:, fixation_index][0]  # find the fixation value
                color = self.fixation_circle_color if is_fixation else self.gaze_circle_color
                if this_frame_pixel.shape[1] > 0:
                    cv2.circle(this_frame, np.array(this_frame_pixel[:, 0], dtype=np.uint8), 10, color, 2)
                self.outputs['gaze_processed_video'] = this_frame.reshape(-1)
                # remove the first video frame from the buffer
                self.inputs.clear_stream_up_to_index(self.video_stream_name, 1)
        self.inputs.clear_stream_up_to(self.frame_gaze_pixel_stream_name, this_frame_timestamp)

    # cleanup is called when the stop button is hit
    def cleanup(self):
        print('Cleanup function is called')

