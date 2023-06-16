from typing import Union, List

from rena.presets.Cmap import Cmap
from rena.presets.GroupEntry import GroupEntry, PlotFormat
from rena.presets.Presets import Presets, PresetType, preprocess_stream_preset, VideoDeviceChannelOrder
from rena.utils.realtime_DSP import DataProcessor
from rena.presets.Presets import Presets, PresetType, preprocess_stream_preset, VideoDeviceChannelOrder, DataType


def get_preset_category(preset_name):
    preset = Presets()
    if preset_name in preset.experiment_presets.keys():
        return PresetType.EXPERIMENT
    else:
        return preset[preset_name].preset_type


def get_all_preset_names():
    return list(Presets().keys())


def get_stream_preset_names():
    return list(Presets().stream_presets.keys())


def get_experiment_preset_names():
    return list(Presets().experiment_presets.keys())


def get_experiment_preset_streams(exp_name):
    return Presets().experiment_presets[exp_name]


def get_stream_preset_info(stream_name, key):
    return Presets().stream_presets[stream_name].__getattribute__(key)


def get_stream_preset_custom_info(stream_name) -> dict:
    return Presets().stream_presets[stream_name].device_info


def set_stream_preset_info(stream_name, key, value):
    setattr(Presets().stream_presets[stream_name], key, value)


def check_preset_exists(stream_name):
    return stream_name in Presets().stream_presets.keys()

def get_stream_nominal_sampling_rate(stream_name):# ->float:
    return Presets().stream_presets[stream_name].nominal_sampling_rate

def get_stream_group_info(stream_name) -> dict[str, GroupEntry]:
    return Presets().stream_presets[stream_name].group_info


def get_stream_a_group_info(stream_name, group_name) -> GroupEntry:
    return Presets().stream_presets[stream_name].group_info[group_name]


def get_group_image_config(stream_name, group_name):
    return Presets().stream_presets[stream_name].group_info[group_name].plot_configs.image_config


def get_is_group_shown(stream_name, group_name) -> List[bool]:
    return Presets().stream_presets[stream_name].group_info[group_name].is_channels_shown


def is_group_image_only(stream_name, group_name):
    return Presets().stream_presets[stream_name].group_info[group_name].is_image_only()


def set_stream_a_group_selected_plot_format(stream_name, group_name, plot_format: Union[str, int, PlotFormat]) -> PlotFormat:
    if isinstance(plot_format, str):
        plot_format = PlotFormat[plot_format.upper()]
    elif isinstance(plot_format, int):
        plot_format = PlotFormat(plot_format)

    Presets().stream_presets[stream_name].group_info[group_name].selected_plot_format = plot_format
    return plot_format


def set_stream_a_group_selected_img_config(stream_name, group_name, height, width, scaling):
    Presets().stream_presets[stream_name].group_info[group_name].plot_configs.image_config.height = height
    Presets().stream_presets[stream_name].group_info[group_name].plot_configs.image_config.width = width
    Presets().stream_presets[stream_name].group_info[group_name].plot_configs.image_config.scaling = scaling


def set_bar_chart_max_min_range(stream_name, group_name, max_range, min_range):
    Presets().stream_presets[stream_name].group_info[group_name].plot_configs.barchart_config.y_max = max_range
    Presets().stream_presets[stream_name].group_info[group_name].plot_configs.barchart_config.y_min = min_range


def get_bar_chart_max_min_range(stream_name, group_name) -> tuple[float, float]:
    return Presets().stream_presets[stream_name].group_info[group_name].plot_configs.barchart_config.y_max, \
           Presets().stream_presets[stream_name].group_info[group_name].plot_configs.barchart_config.y_min


def set_group_image_format(stream_name, group_name, image_format):
    Presets().stream_presets[stream_name].group_info[group_name].plot_configs.image_config.image_format = image_format


def set_group_image_channel_format(stream_name, group_name, channel_format):
    Presets().stream_presets[stream_name].group_info[group_name].plot_configs.image_config.channel_format = channel_format


def get_group_image_valid(stream_name, group_name):
    return Presets().stream_presets[stream_name].group_info[group_name].is_image_valid()


def get_selected_plot_format(stream_name, group_name) -> PlotFormat:
    return Presets().stream_presets[stream_name].group_info[group_name].selected_plot_format


def get_selected_plot_format_index(stream_name, group_name) -> int:
    if Presets().stream_presets[stream_name].group_info[group_name].is_image_only():
        Presets().stream_presets[stream_name].group_info[group_name].selected_plot_format = PlotFormat.IMAGE
    return Presets().stream_presets[stream_name].group_info[group_name].selected_plot_format.value

def get_group_channel_indices(stream_name, group_name) -> list[int]:
    return Presets().stream_presets[stream_name].group_info[group_name].channel_indices


def save_preset(is_async=True):
    Presets().save(is_async=is_async)


def create_default_preset(stream_name, port, preset_type_str, num_channels, nominal_sample_rate: int=None, data_type=DataType.float32):
    if check_preset_exists(stream_name):
        raise ValueError(f'Stream preset with stream name {stream_name} already exists.')
    preset_dict = {'StreamName': stream_name,
                   'ChannelNames': ['channel{0}'.format(i) for i in range(num_channels)],
                   'DataType': data_type,
                   'PortNumber': port}
    if nominal_sample_rate:
        preset_dict['NominalSamplingRate'] = nominal_sample_rate

    stream_preset_dict = preprocess_stream_preset(preset_dict, preset_type_str)
    Presets().add_stream_preset(stream_preset_dict)
    return preset_dict

def pop_group_from_stream_preset(stream_name, group_name) -> GroupEntry:
    return Presets().stream_presets[stream_name].group_info.pop(group_name)


def add_group_entry_to_stream(stream_name, group_entry):
    Presets().stream_presets[stream_name].add_group_entry(group_entry)


def change_group_channels(stream_name, group_name, channel_indices, is_channels_shown):
    Presets().stream_presets[stream_name].group_info[group_name].channel_indices = channel_indices
    Presets().stream_presets[stream_name].group_info[group_name].is_channels_shown = is_channels_shown


def reset_group_data_processors(stream_name, group_name)-> None:
    Presets().stream_presets[stream_name].group_info[group_name].reset_data_processors()

def reset_all_group_data_processors(stream_name)-> None:
    for group_name in Presets().stream_presets[stream_name].group_info:
        reset_group_data_processors(stream_name, group_name)


def get_group_channel_num(stream_name, group_name)-> int:
    return len(Presets().stream_presets[stream_name].group_info[group_name].channel_indices)


def set_group_channel_indices(stream_name, group_name, channel_indices):
    Presets().stream_presets[stream_name].group_info[group_name].channel_indices = channel_indices


def set_group_channel_is_shown(stream_name, group_name, is_shown):
    Presets().stream_presets[stream_name].group_info[group_name].is_channels_shown = is_shown


def change_stream_group_order(stream_name, group_order):
    new_group_info = dict()
    for group_name in group_order:
        new_group_info[group_name] = Presets().stream_presets[stream_name].group_info.pop(group_name)
    Presets().stream_presets[stream_name].group_info = new_group_info

def change_stream_group_name(stream_name, new_group_name, old_group_name):
    try:
        assert new_group_name not in Presets().stream_presets[stream_name].group_info.keys()
    except AssertionError as e:
        raise ValueError(f'New group name {new_group_name} already exists for stream {stream_name}')
    Presets().stream_presets[stream_name].group_info[new_group_name] = Presets().stream_presets[stream_name].group_info.pop(old_group_name)


def pop_stream_preset_from_settings(stream_name):
    return Presets().stream_presets.pop(stream_name)


def spectrogram_time_second_per_segment(stream_name, group_name):
    return Presets().stream_presets[stream_name].group_info[group_name].plot_configs.spectrogram_config.time_per_segment_second


def spectrogram_time_second_overlap(stream_name, group_name):
    return Presets().stream_presets[stream_name].group_info[group_name].plot_configs.spectrogram_config.time_overlap_second


def get_spectrogram_cmap_lut(stream_name, group_name):
    return Presets().stream_presets[stream_name].group_info[group_name].plot_configs.spectrogram_config.cmap.get_lookup_table()

def set_spectrogram_time_per_segment(stream_name, group_name, time_per_segment_second):
    Presets().stream_presets[stream_name].group_info[group_name].plot_configs.spectrogram_config.time_per_segment_second = time_per_segment_second

def set_spectrogram_time_overlap(stream_name, group_name, time_overlap_second):
    Presets().stream_presets[stream_name].group_info[group_name].plot_configs.spectrogram_config.time_overlap_second = time_overlap_second

def get_spectrogram_time_per_segment(stream_name, group_name):
    return Presets().stream_presets[stream_name].group_info[group_name].plot_configs.spectrogram_config.time_per_segment_second


def get_spectrogram_time_overlap(stream_name, group_name):
    return Presets().stream_presets[stream_name].group_info[group_name].plot_configs.spectrogram_config.time_overlap_second

def set_spectrogram_cmap(stream_name: str, group_name: str, cmap: Cmap):
    Presets().stream_presets[stream_name].group_info[group_name].plot_configs.spectrogram_config.cmap = cmap


def get_spectrogram_percentile_level_min(stream_name, group_name):
    return Presets().stream_presets[stream_name].group_info[group_name].plot_configs.spectrogram_config.percentile_level_min

def get_spectrogram_percentile_level_max(stream_name, group_name):
    return Presets().stream_presets[stream_name].group_info[group_name].plot_configs.spectrogram_config.percentile_level_max

def set_spectrogram_percentile_level_min(stream_name, group_name, percentile_level_min):
    Presets().stream_presets[stream_name].group_info[group_name].plot_configs.spectrogram_config.percentile_level_min = percentile_level_min

def set_spectrogram_percentile_level_max(stream_name, group_name, percentile_level_max):
    Presets().stream_presets[stream_name].group_info[group_name].plot_configs.spectrogram_config.percentile_level_max = percentile_level_max


def set_video_scale(video_device_name, scale: float):
    Presets().stream_presets[video_device_name].video_scale = scale


def set_video_channel_order(video_device_name, channel_order: Union[str, int, VideoDeviceChannelOrder]) -> VideoDeviceChannelOrder:
    if isinstance(channel_order, str):
        channel_order = VideoDeviceChannelOrder[channel_order.upper()]
    elif isinstance(channel_order, int):
        channel_order = VideoDeviceChannelOrder(channel_order)

    Presets().stream_presets[video_device_name].channel_order = channel_order
    return channel_order


def get_video_scale(video_device_name) -> float:
    return Presets().stream_presets[video_device_name].video_scale

def get_video_channel_order(video_device_name) -> VideoDeviceChannelOrder:
    return Presets().stream_presets[video_device_name].channel_order

def is_video_webcam(video_device_name) -> bool:
    return Presets().stream_presets[video_device_name].preset_type == PresetType.WEBCAM

def get_video_device_id(video_device_name) -> int:
    return Presets().stream_presets[video_device_name].video_id


def get_group_data_processors(stream_name, group_name) ->list[DataProcessor]:
    return Presets().stream_presets[stream_name].group_info[group_name].data_processors

def add_data_processor_to_group_entry(stream_name, group_name, data_processor:DataProcessor) ->None:
    Presets().stream_presets[stream_name].group_info[group_name].data_processors.append(data_processor)

def remove_data_processor_to_group_entry(stream_name, group_name, data_processor: DataProcessor) ->None:
    Presets().stream_presets[stream_name].group_info[group_name].data_processors.remove(data_processor)