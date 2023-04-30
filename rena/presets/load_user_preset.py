from exceptions.exceptions import InvalidPresetErrorChannelNameOrNumChannel
from rena import config
from rena.config import DEFAULT_CHANNEL_DISPLAY_NUM, default_group_name
from rena.presets.GroupEntry import GroupEntry
from rena.utils.data_utils import convert_dict_keys_to_snake_case


# def get_presets_by_category(setting_category):
#     assert setting_category == 'streampresets' or setting_category == 'experimentpresets'
#     group = 'presets/{0}'.format(setting_category)
#     config.settings.beginGroup(group)
#     presets = list(config.settings.childGroups())
#     config.settings.endGroup()
#     return presets

# def get_video_device_names():
#     return config.settings.value('video_device')

# def get_experiment_preset_names():
#     config.settings.beginGroup('presets/experimentpresets')
#     experiment_preset_names = list(config.settings.childGroups())
#     config.settings.endGroup()
#     return experiment_preset_names


# def collect_stream_group_info(stream_name, group_name):
#     rtn = dict()
#     config.settings.beginGroup('presets/streampresets/{0}/GroupInfo/{1}'.format(stream_name, group_name))
#     for keys in config.settings.childKeys():
#         rtn[keys] = config.settings.value(keys)
#     # for value in config.settings.childGroups():
#     #     rtn[value] = dict([(k, config.settings.value(k)) for k in config.settings.childKeys()])
#     #     rtn['is_channels_shown'] = [bool(int(x)) for x in rtn['is_channels_shown']]
#     config.settings.endGroup()
#     rtn['plot_format'] = collect_stream_group_plot_format(stream_name, group_name)
#     rtn['is_channels_shown'] = [any_to_bool(x) for x in rtn['is_channels_shown']]
#     rtn['channel_indices'] = [int(i) for i in rtn['channel_indices']]
#     rtn['is_image_only'] = len(rtn['channel_indices']) > config.settings.value("max_timeseries_num_channels")
#
#     return rtn

# def any_to_bool(x):
#     if type(x) == int:
#         return bool(x)
#     elif type(x) == str:
#         if str.isdigit(x):
#             return bool(int(x))
#         else:
#             return bool(json.loads(x.lower()))

# def collect_stream_group_plot_format(stream_name, group_name):
#     rtn = dict()
#     config.settings.beginGroup('presets/streampresets/{0}/{1}/{2}/plot_format'.
#                                format(stream_name, 'GroupInfo', group_name,
#                                       'plot_format'))
#     for plot_format_name in config.settings.childGroups():
#         rtn[plot_format_name] = dict()
#
#         config.settings.beginGroup(plot_format_name)
#         for format_info_key in config.settings.childKeys():
#             rtn[plot_format_name][format_info_key] = config.settings.value(format_info_key)
#         config.settings.endGroup()
#
#     rtn['bar_chart']['y_max'] = float(rtn['bar_chart']['y_max'])
#     rtn['bar_chart']['y_min'] = float(rtn['bar_chart']['y_min'])
#
#     config.settings.endGroup()
#     return rtn

    # return config.settings.value('presets/streampresets/{0}/GroupInfo/{1}/{2}'.format(stream_name, group_name, 'plot_format'))

# def set_stream_group_plot_format(stream_name, group_name, ):



# def get_complete_stream_preset_info(stream_name):
#     rtn = dict()
#     config.settings.beginGroup('presets/streampresets/{0}'.format(stream_name))
#     for field in config.settings.childKeys():
#         rtn[field] = config.settings.value(field)
#     config.settings.endGroup()
#     rtn['GroupInfo'] = collect_stream_all_groups_info(stream_name)
#     return rtn

# def get_childKeys_for_group(group):
#     config.settings.beginGroup(group)
#     rtn = config.settings.childKeys()
#     config.settings.endGroup()
#     return rtn

# def get_childGroups_for_group(group):
#     config.settings.beginGroup(group)
#     rtn = config.settings.childGroups()
#     config.settings.endGroup()
#     return rtn


# def get_all_lsl_device_preset_names():
#     return get_childGroups_for_group('presets/streampresets')


# def change_group_name(this_group_info, new_group_name, old_group_name, stream_name):
#     config.settings.remove('presets/streampresets/{0}/GroupInfo/{1}'.format(stream_name, old_group_name))
#     update_group_info(this_group_info, stream_name, new_group_name)


# def update_group_info(this_group_info, stream_name, group_name):
#     config.settings.remove('presets/streampresets/{0}/GroupInfo/{1}'.format(stream_name, group_name))
#     config.settings.beginGroup('presets/{0}'.format('streampresets'))
#     for group_info_key, group_info_value in this_group_info.items():
#         if group_info_key != 'plot_format':
#             config.settings.setValue(
#                 '{0}/GroupInfo/{1}/{2}'.format(stream_name, group_name, group_info_key), group_info_value)
#         else:
#             for plot_format_name, plot_format_info_dict in group_info_value.items():
#                 for plot_format_info_key, plot_format_info_value in plot_format_info_dict.items():
#                     config.settings.setValue('{0}/GroupInfo/{1}/{2}/{3}/{4}'.
#                                              format(stream_name,
#                                                     group_name,  # group name
#                                                     group_info_key,
#                                                     plot_format_name,  # plot format file
#                                                     plot_format_info_key),  # plot format name
#                                              plot_format_info_value)  # plot format value
#     config.settings.endGroup()


# def export_preset_to_settings(preset, setting_category):
#     assert setting_category == 'streampresets' or setting_category == 'experimentpresets'
#     if setting_category == 'experimentpresets':
#         config.settings.setValue('presets/experimentpresets/{0}/PresetStreamNames'.format(preset[0]), preset[1])
#     else:
#         config.settings.beginGroup('presets/{0}'.format(setting_category))
#
#         for preset_key, value in preset.items():
#             if preset_key != 'GroupInfo':
#                 config.settings.setValue('{0}/{1}'.format(preset['StreamName'], preset_key), value)
#
#         for group_name, group_info_dict in preset['GroupInfo'].items():
#             for group_info_key, group_info_value in group_info_dict.items():
#                 if group_info_key!='plot_format':
#                     config.settings.setValue('{0}/GroupInfo/{1}/{2}'.format(preset['StreamName'], group_name, group_info_key), group_info_value)
#                 else:
#                     for plot_format_name, plot_format_info_dict in group_info_value.items():
#                         for plot_format_info_key, plot_format_info_value in plot_format_info_dict.items():
#                             # config.settings.setValue('{0}/GroupInfo/GroupName{1}/{2}/{3}'.
#                             #                          format(preset['StreamName'],
#                             #                                 group_info_dict['group_index'],  # group name
#                             #                                 group_info_key,
#                             #                                 'selected'
#                             #                                 ),  # plot format name
#                             #                                     'time_series')
#                             config.settings.setValue('{0}/GroupInfo/{1}/{2}/{3}/{4}'.
#                                                      format(preset['StreamName'],
#                                                             group_name,  # group name
#                                                             group_info_key,
#                                                             plot_format_name, # plot format file
#                                                             plot_format_info_key), # plot format name
#                                                             plot_format_info_value) # plot format value
#
#         config.settings.endGroup()


# def load_all_presets(preset_roots):
#     preset_file_names = os.listdir(preset_roots)
#     preset_file_paths = [os.path.join(preset_roots, x) for x in preset_file_names]
#     presets = Presets()
#     for pf_path in preset_file_paths:
#         loaded_preset_dict = json.load(open(pf_path))
#
#         presets[loaded_preset_dict['StreamName']]
#
#         preset_dict = validate_preset(loaded_preset_dict)
#
#
#         stream_name = preset_dict['StreamName']
#         presets[stream_name] = preset_dict
#     return presets

# def load_stream_presets(preset_roots, presets, network_interface):
#     """
#     load all presets from a directory
#
#     @param preset_roots:
#     @return:
#     """
#     preset_file_names = os.listdir(preset_roots)
#     preset_file_paths = [os.path.join(preset_roots, x) for x in preset_file_names]
#     for pf_path in preset_file_paths:
#         loaded_preset_dict = json.load(open(pf_path))
#
#         stream_preset_dict = validate_preset_json_preset(loaded_preset_dict)
#         stream_preset_dict['networking_interface'] = network_interface
#         stream_preset_dict = process_plot_group_json_preset(stream_preset_dict)
#         presets.add_stream_preset(stream_preset_dict)
#
#     return presets

# def load_all_json_presets(preset_root, presets):
#     presets = load_stream_presets(os.path.join(preset_root, 'LSLPresets'), presets, 'LSL')
#     presets = load_stream_presets(os.path.join(preset_root, 'ZMQPresets'), presets, 'ZMQ')
#     presets = load_stream_presets(os.path.join(preset_root, 'DevicePresets'), presets, 'Device')
#     presets = load_all_experiment_presets(os.path.join(preset_root, 'ExperimentPresets'), presets)
#     return presets

# def load_all_Device_presets(device_preset_roots='../Presets/DevicePresets'):
#     preset_file_names = os.listdir(device_preset_roots)
#     preset_file_paths = [os.path.join(device_preset_roots, x) for x in preset_file_names]
#     presets = {}
#     for pf_path in preset_file_paths:
#         loaded_preset_dict = json.load(open(pf_path))
#         preset_dict = add_keys_to_preset(loaded_preset_dict)
#         stream_name = preset_dict['StreamName']
#         presets[stream_name] = preset_dict
#     return presets


# def load_all_experiment_presets(exp_preset_roots, presets):
#     preset_file_names = os.listdir(exp_preset_roots)
#     preset_file_paths = [os.path.join(exp_preset_roots, x) for x in preset_file_names]
#     for pf_path in preset_file_paths:
#         loaded_preset_dict = json.load(open(pf_path))
#         presets.add_experiment_preset(loaded_preset_dict['ExperimentName'], loaded_preset_dict['PresetStreamNames'])
#     return presets


# def validate_preset(preset_dict):
#     if 'GroupInfo' in preset_dict.keys():
#         try:
#             assert 'ChannelNames' in preset_dict.keys() or 'NumChannels' in preset_dict.keys()
#         except AssertionError:
#             raise ValueError('Preset with stream name {0} has GroupChnanelsInPlot field. In this case, this preset must also have either ChannelNames field or NumChannels field'
#                              '. This is likely a problem with the default presets or bug in preset creation'.format(preset_dict['StreamName']))
#     if 'ChannelNames' in preset_dict.keys() and 'NumChannels' not in preset_dict.keys():
#         preset_dict['NumChannels'] = len(preset_dict['ChannelNames'])
#     elif 'NumChannels' in preset_dict.keys() and 'ChannelNames' not in preset_dict.keys():
#         preset_dict['ChannelNames'] = ['Channel{0}'.format(x) for x in list(range(int(preset_dict['NumChannels'])))]
#     else:
#         raise InvalidPresetErrorChannelNameOrNumChannel(preset_dict['StreamName'])
#     if 'GroupInfo' not in preset_dict.keys():
#         preset_dict['GroupInfo'] = None
#         preset_dict['GroupFormat'] = None
#     if 'GroupFormat' not in preset_dict.keys():
#         preset_dict['GroupFormat'] = None
#     if 'NominalSamplingRate' not in preset_dict.keys():
#         preset_dict['NominalSamplingRate'] = 1
#     if 'DisplayDuration' not in preset_dict.keys():
#         preset_dict['DisplayDuration'] = config.settings.value('viz_display_duration')
#
#     if 'NetworkingInterface' not in preset_dict.keys():
#         preset_dict['NetworkingInterface'] = 'LSL'  # default is LSL
#     if 'PortNumber' not in preset_dict.keys():
#         preset_dict['PortNumber'] = None
#     if 'DataType' not in preset_dict.keys():
#         preset_dict['DataType'] = 'float32'
#     return preset_dict


# def create_default_group_info(channel_num, group_name):
#     # create groupinfo from 0 to x
#     # if channel num is greater than 100, we hide the rest
#     if channel_num <= DEFAULT_CHANNEL_DISPLAY_NUM_PER_GROUP:
#         is_channels_shown = [1 for c in range(0, channel_num)]
#     else:
#         is_channels_shown = [1 for c in range(0, DEFAULT_CHANNEL_DISPLAY_NUM_PER_GROUP)]
#         is_channels_shown.extend([0 for c in range(DEFAULT_CHANNEL_DISPLAY_NUM_PER_GROUP, channel_num)])
#
#     return {
#         group_name: {
#             'selected_plot_format': 0,
#             "plot_format": default_plot_format,
#             "channel_indices": [channel_index for channel_index in range(0, channel_num)],
#             "is_channels_shown": is_channels_shown,
#             "group_description": "",
#             "is_image_only": channel_num > MAX_TIMESERIES_NUM_CHANNELS_PER_GROUP
#                 }
#             }

def create_default_group_info(channel_num: int, group_name: str =config.default_group_name,
                              channel_indices=None, is_channels_shown=None):
    """
    create default group info from channel num
    @param channel_num:
    @param group_name: default is the default group name defined in config.py. This is used when calling process_plot_group_json_preset.
    This is also used in StreamWidget to create the default group info.
    @return:
    """
    channel_indices = [channel_index for channel_index in range(0, channel_num)] if channel_indices is None else channel_indices
    group_entry = GroupEntry(group_name=group_name, channel_indices=channel_indices, is_channels_shown=is_channels_shown)
    return {group_name: group_entry}


# def update_selected_plot_format(stream_name, group_name, selected_format: int):
#     config.settings.setValue('presets/streampresets/{0}/GroupInfo/{1}/selected_plot_format'.format(stream_name, group_name, selected_format), selected_format)


# plot_format
# {
# time_series:{}
# image: {}
# bar plot : {}
# }

def process_plot_group_json_preset(preset_dict):
    """
    create group info from the json format
    Note on the json format:
    the group info is a list of integers, where each integer is the indices at which a new group starts

    Example:
        1. for a stream that has eight channels, a group info defined as follows
        [2, 4, 6]
        will create four groups, where the first group has two channels, the second group has two channels, the third group has two channels, and the fourth group has two channels

        2. for a stream with 65 channels, a group info defined as follows
        [1]
        will create two groups, where the first group has one channel, and the second group has 63 channels
        The first channel could be the time series, and the rest are EEG. The time series obviously should be plotted in a separate plot
        than EEG because they have very different numeric ranges.
    """
    channel_num = preset_dict['num_channels']
    if preset_dict['group_info'] is None:  # group_info will be none if the json file does not contain group_info. In that case, a none group_info will added when calling validate_preset_json_preset
        preset_dict['group_info'] = create_default_group_info(channel_num)
    else:  # the only information the preset conveys is how to divide the channels into groups, only consecutive channels can be grouped together
        plot_group_slice = []
        head = 0
        for x in preset_dict['group_info']:
            plot_group_slice.append((head, x))
            head = x
        if head != channel_num:
            plot_group_slice.append(
                (head, channel_num))  # append the last group
            # create GroupInfo from 0 to x
            # preset_dict['GroupInfo'] = [[channel_index for channel_index in range(0, len(preset_dict['ChannelNames']))]]

        # if preset_dict['GroupFormat'] is None or 'GroupFormat' not in preset_dict:  # default is always time series
        #     preset_dict['GroupFormat'] = ['time_series'] * (len(preset_dict['GroupInfo']))

        preset_dict['group_info'] = dict()
        num_shown_channel = 0
        for i, group in enumerate(plot_group_slice):
            channel_indices = list(range(*group))
            num_available_ch_shown = DEFAULT_CHANNEL_DISPLAY_NUM - num_shown_channel
            if num_available_ch_shown <= 0:
                is_channels_shown = [True] * len(channel_indices)
                # is_channels_shown = [0 for c in range(len(channel_indices))]
            else:
                # is_channels_shown = [1 for c in range(min(len(channel_indices), DEFAULT_CHANNEL_DISPLAY_NUM))]
                # is_channels_shown += [0] * (len(channel_indices) - len(is_channels_shown))  # won't pad if len(channel_indices) - len(is_channels_shown) is negative

                is_channels_shown = [True] * min(len(channel_indices), DEFAULT_CHANNEL_DISPLAY_NUM)
                is_channels_shown += [False] * (len(channel_indices) - len(is_channels_shown))
                num_shown_channel += min(len(channel_indices), DEFAULT_CHANNEL_DISPLAY_NUM)

            # preset_dict['GroupInfo'][f"{default_group_name}{i}"] = \
            #     {
            #         'selected_plot_format': 0,
            #         "plot_format": default_plot_format,
            #         "channel_indices": channel_indices,
            #         "is_channels_shown": is_channels_shown,
            #         "group_description": ""
            #     }
            preset_dict['group_info'][f"{default_group_name}{i}"] = GroupEntry(
                group_name=f"{default_group_name}{i}",
                channel_indices=channel_indices,
                is_channels_shown=is_channels_shown)  # nothing is loaded for plot config

            # preset_dict['GroupInfo'][f"{default_group_name}{i}"] = \
            #     {
            #         "plot_format": default_plot_format,
            #         "channel_indices": channel_indices,
            #         "is_channels_shown": is_channels_shown,
            #         "group_description": ""
            #     }

    return preset_dict

# def get_channel_info(stream_name):
#     rtn = dict()
#     config.settings.beginGroup('presets/streampresets/{0}/GroupInfo'.format(stream_name))
#     for group_name in config.settings.childGroups():
#         config.settings.beginGroup(group_name)
#         rtn[group_name] = dict([(k, config.settings.value(k)) for k in config.settings.childKeys()])
#         rtn[group_name]['is_channels_shown'] = [bool(int(x)) for x in rtn[group_name]['is_channels_shown']]
#         config.settings.endGroup()
#     config.settings.endGroup()
#     return rtn


# def is_channel_in_group(channel_index, group_name, stream_name):
#     """
#     channel name cannot duplicate so we use index for finding a specific channel.
#     group name
#     """
#     config.settings.beginGroup('presets/streampresets/{0}/GroupInfo/{1}'.format(stream_name, group_name))
#     channel_indices = config.settings.value('channel_indices')
#     config.settings.endGroup()
#     return channel_index in channel_indices

# def is_channel_displayed(channel_index, group_name, stream_name):
#     config.settings.beginGroup('presets/streampresets/{0}/GroupInfo/{1}'.format(stream_name, group_name))
#     channel_index_in_settings = [int(x) for x in config.settings.value('channel_indices')].index(channel_index)
#     is_channel_shown = config.settings.value('is_channels_shown')[channel_index_in_settings]
#     config.settings.endGroup()
#     return is_channel_shown == '1'

# def set_channel_displayed(is_display, channel_index, group_name, stream_name):
#     config.settings.beginGroup('presets/streampresets/{0}/GroupInfo/{1}'.format(stream_name, group_name))
#     channel_index_in_settings = [int(x) for x in config.settings.value('channel_indices')].index(channel_index)
#
#     new_is_channels_shown = config.settings.value('is_channels_shown')
#     new_is_channels_shown[channel_index_in_settings] = '1' if is_display else '0'
#
#     config.settings.setValue('is_channels_shown', new_is_channels_shown)
#     config.settings.endGroup()


# def get_channel_num(stream_name):
#     channel_num = config.settings.value('presets/streampresets/{0}/{1}'.format(stream_name, 'NumChannels'))
#     return channel_num


#####################################################################

# def set_plot_image_w_h(stream_name, group_name, height, width, scaling_factor):
#     config.settings.beginGroup('presets/streampresets/{0}/GroupInfo/{1}/plot_format/image'.format(stream_name, group_name))
#     config.settings.setValue('height', height)
#     config.settings.setValue('width', width)
#     config.settings.setValue('scaling_factor', scaling_factor)
#
#     config.settings.endGroup()

#####################################################################
def validate_preset_json_preset(preset_dict):
    if 'GroupInfo' in preset_dict.keys():
        try:
            assert 'ChannelNames' in preset_dict.keys() or 'NumChannels' in preset_dict.keys()
        except AssertionError:
            raise ValueError('Preset with stream name {0} has GroupChnanelsInPlot field. In this case, this preset must also have either ChannelNames field or NumChannels field'
                             '. This is likely a problem with the default presets or bug in preset creation'.format(preset_dict['StreamName']))
    else:
        preset_dict['GroupInfo'] = None
    if 'ChannelNames' in preset_dict.keys() and 'NumChannels' not in preset_dict.keys():
        preset_dict['NumChannels'] = len(preset_dict['ChannelNames'])
    elif 'NumChannels' in preset_dict.keys() and 'ChannelNames' not in preset_dict.keys():
        preset_dict['ChannelNames'] = ['Channel{0}'.format(x) for x in list(range(int(preset_dict['NumChannels'])))]
    else:
        raise InvalidPresetErrorChannelNameOrNumChannel(preset_dict['StreamName'])
    # if 'GroupInfo' not in preset_dict.keys():
    #     preset_dict['GroupInfo'] = None
    #     preset_dict['GroupFormat'] = None
    # if 'GroupFormat' not in preset_dict.keys():
    #     preset_dict['GroupFormat'] = None
    # if 'NominalSamplingRate' not in preset_dict.keys():
    #     preset_dict['NominalSamplingRate'] = 1
    # if 'DisplayDuration' not in preset_dict.keys():
    #     preset_dict['DisplayDuration'] = config.settings.value('viz_display_duration')

    # if 'NetworkingInterface' not in preset_dict.keys():
    #     preset_dict['NetworkingInterface'] = 'LSL'  # default is LSL
    # if 'PortNumber' not in preset_dict.keys():
    #     preset_dict['PortNumber'] = None
    # if 'DataType' not in preset_dict.keys():
    #     preset_dict['DataType'] = 'float32'
    preset_dict = convert_dict_keys_to_snake_case(preset_dict)
    return preset_dict
