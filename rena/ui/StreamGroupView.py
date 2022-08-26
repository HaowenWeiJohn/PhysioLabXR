import sys
from collections import deque

import PyQt5
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *

from rena import config
from rena.config_ui import *
from rena.ui.OptionsWindowPlotFormatWidget import OptionsWindowPlotFormatWidget
from rena.ui_shared import CHANNEL_ITEM_IS_DISPLAY_CHANGED
from rena.utils.settings_utils import get_stream_preset_info, is_group_shown
from rena.utils.ui_utils import dialog_popup
from PyQt5 import QtCore, QtGui, QtWidgets


## Reference:
## https://stackoverflow.com/questions/13662020/how-to-implement-itemchecked-and-itemunchecked-signals-for-qtreewidget-in-pyqt4

class GroupItem(QTreeWidgetItem):
    item_type = 'group'

    def __init__(self, parent, is_shown, plot_format, stream_name, group_name):
        super().__init__(parent)
        self.is_shown = is_shown  # show the channel plot or not
        self.plot_format = plot_format
        self.stream_name = stream_name
        self.group_name = group_name
        self.setText(0, group_name)

        self.OptionsWindowPlotFormatWidget = OptionsWindowPlotFormatWidget(self.stream_name, self.group_name)



    def setData(self, column, role, value):
        check_state_before = self.checkState(column)
        super(GroupItem, self).setData(column, role, value)
        check_state_after = self.checkState(column)

        if check_state_before != check_state_after:
            if check_state_after == Qt.Checked or check_state_after == Qt.PartiallyChecked:
                self.display=True
                self.setForeground(0, QBrush(QColor(color_green)))
            else:
                self.display=False
                self.setForeground(0, QBrush(QColor(color_white)))


class ChannelItem(QTreeWidgetItem):
    def __init__(self, parent, is_shown, lsl_index, channel_name):
        super().__init__(parent)
        self.is_shown = is_shown  # show the channel plot or not
        self.lsl_index = lsl_index
        self.most_recent_change = None
        self.channel_name = channel_name
        self.setText(0, channel_name)
        self.setText(1, '['+str(lsl_index)+']')


    def setData(self, column, role, value):
        parent_check_state_before = self.parent().checkState(column)
        item_check_state_before = self.checkState(column)

        super(ChannelItem, self).setData(column, role, value)
        item_check_state_after = self.checkState(column)
        parent_check_state_after = self.parent().checkState(column)


        if role == QtCore.Qt.EditRole:
            pass
            # editing the name


        if role == QtCore.Qt.CheckStateRole and item_check_state_before != item_check_state_after:
            # set text to green
            if item_check_state_after == Qt.Checked or item_check_state_after == Qt.PartiallyChecked:
                self.display = True
                self.setForeground(0, QBrush(QColor(color_green)))
            else:
                self.display = False
                self.setForeground(0, QBrush(QColor(color_white)))

            if parent_check_state_after != parent_check_state_before:
                if parent_check_state_after == Qt.Checked or parent_check_state_after == Qt.PartiallyChecked:
                    self.parent().display = True
                    self.parent().setForeground(0, QBrush(QColor(color_green)))
                else:
                    self.parent().display = False
                    self.parent().setForeground(0, QBrush(QColor(color_white)))


class StreamGroupView(QTreeWidget):
    selection_changed_signal = QtCore.pyqtSignal(str)
    update_info_box_signal = QtCore.pyqtSignal(str)

    channel_parent_group_changed_signal = QtCore.pyqtSignal(tuple)
    channel_is_display_changed_signal = QtCore.pyqtSignal(tuple)

    def __init__(self, parent, stream_name, group_info):
        # super(SignalTreeViewWindow, self).__init__(parent=parent)
        super().__init__()
        self.parent = parent
        self.stream_name = stream_name

        # self.model = QStandardItemModel()
        # self.model.setHorizontalHeaderLabels(['Display', 'Name'])

        # self.header().setDefaultSectionSize(180)
        # self.setHeaderHidden(True)
        self.setHeaderLabels(["Name", "LSL Index"])

        # self.setModel(self.model)
        self.groups_widgets = []
        self.channel_widgets = []
        self.stream_root = None
        self.create_tree_view(group_info)

        # self.setSelectionMode(self.SingleSelection)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)

        # selections:
        self.selection_state = nothing_selected
        self.selected_groups = []
        self.selected_channels = []

        # self.resize(500, 200)

        # helper fieds
        self.dragged = None

        self.resizeColumnToContents(0)

        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.itemDoubleClicked.connect(self.item_double_clicked_handler)

    def item_double_clicked_handler(self, item:QTreeWidgetItem, column):
        if column == 0:
            self.editItem(item, column)
        else:
            pass


    def clear_tree_view(self):
        self.selection_state = nothing_selected
        self.selected_groups = []
        self.selected_channels = []
        self.selectionModel().selectionChanged.disconnect(self.selection_changed)
        self.itemChanged[QTreeWidgetItem, int].disconnect(self.item_changed)
        self.clear()

    def create_tree_view(self, group_info, image_ir_only=False):
        self.stream_root = QTreeWidgetItem(self)
        self.stream_root.item_type = 'stream_root'
        self.stream_root.setText(0, self.stream_name)
        self.stream_root.setFlags(self.stream_root.flags()
                                  & (~Qt.ItemIsDragEnabled)
                                  & (~Qt.ItemIsSelectable) | Qt.ItemIsEditable)
        # self.stream_root.channel_group.setEditable(False)

        # get_childGroups_for_group('presets/')
        for group_name, group_values in group_info.items():
            # channel_group = self.add_channel_item(parent_item=self.stream_root, display_text=group_name, display=group_values['plot_format'])

            # group = self.add_item(parent_item=self.stream_root,
            #                               display_text=group_name,
            #                               plot_format=group_values['plot_format'],
            #                               item_type='group')
            group = self.add_group_item(parent_item=self.stream_root,
                                        group_name=group_name,
                                        plot_format=group_values['plot_format'])
            # self.groups_widgets.append(group)
            for channel_index_in_group, channel_index in enumerate(group_values['channel_indices']):
                # print(channel_index)
                # channel = self.add_item(parent_item=group,
                #                         display_text=get_stream_preset_info(self.stream_name, key='ChannelNames')[int(channel_index)],
                #                         item_type='channel',
                #                         display=group_values['is_channels_shown'][channel_index_in_group],
                #                         item_index=channel_index)
                channel = self.add_channel_item(parent_item=group,
                                                channel_name=
                                                get_stream_preset_info(self.stream_name, key='ChannelNames')[
                                                    int(channel_index)],
                                                is_shown=group_values['is_channels_shown'][channel_index_in_group],
                                                lsl_index=channel_index)

                channel.setFlags(channel.flags() & (~Qt.ItemIsDropEnabled))
                # self.channel_widgets.append(channel)
        self.expandAll()
        self.selectionModel().selectionChanged.connect(self.selection_changed)
        self.itemChanged[QTreeWidgetItem, int].connect(self.item_changed)

    def startDrag(self, actions):

        # self.selected_items = self.selectedItems()
        # # cannot drag groups and items at the same time:
        # self.moving_groups = False
        # self.moving_channels = False
        # for selected_item in self.selected_items:
        #     if selected_item.item_type == 'group':
        #         self.moving_groups = True
        #     if selected_item.item_type == 'channel':
        #         self.moving_channels = True
        #
        # if self.moving_groups and self.moving_channels:
        #     dialog_popup('Cannot move group and channels at the same time')
        #     self.clearSelection()
        #     return
        # if self.moving_groups:  # is moving groups, we cannot drag one group into another
        #     [group_widget.setFlags(group_widget.flags() & (~Qt.ItemIsDropEnabled)) for group_widget in
        #      self.groups_widgets]
        # if self.moving_channels:
        #     self.stream_root.setFlags(self.stream_root.flags() & (~Qt.ItemIsDropEnabled))
        #
        if self.selection_state==mix_selected:
            dialog_popup('Cannot move group and channels at the same time')
            self.clearSelection()
            return
        if self.selection_state == group_selected or self.selection_state == groups_selected:  # is moving groups, we cannot drag one group into another
            [group_widget.setFlags(group_widget.flags() & (~Qt.ItemIsDropEnabled)) for group_widget in
             self.groups_widgets]
        if self.selection_state==channel_selected or self.selection_state==channels_selected:
            self.stream_root.setFlags(self.stream_root.flags() & (~Qt.ItemIsDropEnabled))
        #
        # self.clearSelection()

        self.disconnect_selection_changed()
        QTreeWidget.startDrag(self, actions)
        # self.clearSelection()
        self.reconnect_selection_changed()
        self.dragged = self.selectedItems()


    def dropEvent(self, event):
        drop_target = self.itemAt(event.pos())
        if drop_target == None:
            self.reset_drag_drop()
            return
        elif drop_target.data(0, 0) == self.stream_name:
            self.reset_drag_drop()
            return
        else:
            QTreeWidget.dropEvent(self, event)
            self.reset_drag_drop()

            # check empty group
            self.remove_empty_groups()
            print(drop_target.checkState(0))

        if len(self.selected_channels) == 1 and type(self.selected_channels[0]) is ChannelItem:  # only one channel is being dragged
            target_parent_group = drop_target.parent().data(0, 0) if type(drop_target) is ChannelItem else drop_target.data(0, 0)
            channel_index = self.selected_channels[0].lsl_index
            self.channel_parent_group_changed_signal.emit((channel_index, target_parent_group))


    # def mousePressEvent(self, *args, **kwargs):
    #     super(StreamGroupView, self).mousePressEvent(*args, **kwargs)
    #     self.reset_drag_drop()

    def reset_drag_drop(self):
        self.stream_root.setFlags(self.stream_root.flags() | Qt.ItemIsDropEnabled)
        [group_widget.setFlags(group_widget.flags() | Qt.ItemIsDropEnabled) for group_widget in
         self.groups_widgets]

        # self.moving_groups = False
        # self.moving_channels = False
        # self.stream_root.setCheckState(0, Qt.Checked)

    def add_item(self, parent_item, display_text, item_type, plot_format=None, display=None, item_index=None):
        item = QTreeWidgetItem(parent_item)
        item.setText(0, str(display_text))
        item.item_type = item_type
        item.display = display
        if plot_format is not None:
            item.plot_format = 'time_series'
        if item_index is not None:
            item.item_index = item_index
        if display is not None:
            if display == 1:
                item.setForeground(0, QBrush(QColor(color_green)))
                item.setCheckState(0, Qt.Checked)
            else:
                item.setCheckState(0, Qt.Unchecked)
        else:
            item.setCheckState(0, Qt.Unchecked)
        # item.setForeground(0, QBrush(QColor("#123456")))
        # channel.setCheckState(0, Qt.Unchecked)
        # channel_group.setText(1, group_name)
        # channel_group.setEditable(False)
        item.setFlags(
            item.flags()
            | Qt.ItemIsTristate
            | Qt.ItemIsUserCheckable
            | Qt.ItemIsEditable
            | Qt.ItemIsDragEnabled
            | Qt.ItemIsDropEnabled
        )

        return item

    def add_channel_item(self, parent_item, channel_name, is_shown, lsl_index):
        item = ChannelItem(parent=parent_item, is_shown=is_shown, lsl_index=lsl_index, channel_name=channel_name)
        # item.setText(0, channel_name)
        if is_shown == 1:
            item.setForeground(0, QBrush(QColor(color_green)))
            item.setCheckState(0, Qt.Checked)
        else:
            item.setCheckState(0, Qt.Unchecked)

        item.setFlags(
            item.flags()
            | Qt.ItemIsTristate
            | Qt.ItemIsUserCheckable
            | Qt.ItemIsEditable
            | Qt.ItemIsDragEnabled
            | Qt.ItemIsDropEnabled
        )
        # item.emitDataChanged()
        self.channel_widgets.append(item)
        return item

    def add_group_item(self, parent_item, group_name, plot_format):
        is_shown = is_group_shown(group_name, self.stream_name)
        item = GroupItem(parent=parent_item, is_shown=is_shown, plot_format=plot_format, stream_name=self.stream_name, group_name=group_name)
        # item.setText(0, group_name)
        if is_shown:
            item.setForeground(0, QBrush(QColor(color_green)))
            item.setCheckState(0, Qt.Checked)
        else:
            item.setCheckState(0, Qt.Unchecked)

        item.setFlags(
            item.flags()
            | Qt.ItemIsTristate
            | Qt.ItemIsUserCheckable
            | Qt.ItemIsEditable
            | Qt.ItemIsDragEnabled
            | Qt.ItemIsDropEnabled
        )
        self.groups_widgets.append(item)
        return item

    # def add_group(self, display_text, item_type='group', display=1, item_index=None):
    #     new_group = self.add_item(self.stream_root, display_text, item_type, plot_format='time_series', display=display,
    #                               item_index=item_index)
    #     self.groups_widgets.append(new_group)
    #     return new_group

    def get_group_names(self):
        group_names = []
        for index in range(0, self.stream_root.childCount()):
            group_names.append(self.stream_root.child(index).data(0, 0))
        return group_names

    def get_all_child(self, item):
        child_count = item.childCount()
        children = []
        for child_index in range(child_count):
            children.append(item.child(child_index))
        return children

    def remove_empty_groups(self):
        children_num = self.stream_root.childCount()
        empty_groups = []
        for child_index in range(0, children_num):
            group = self.stream_root.child(child_index)
            if group.childCount() == 0:
                empty_groups.append(group)
        for empty_group in empty_groups:
            self.groups_widgets.remove(empty_group)
            self.stream_root.removeChild(empty_group)

    def change_parent(self, item, new_parent):
        old_parent = item.parent()
        ix = old_parent.indexOfChild(item)
        item_without_parent = old_parent.takeChild(ix)
        new_parent.addChild(item_without_parent)

    @QtCore.pyqtSlot()
    def selection_changed(self):
        # print('TEST SELECTIONS')
        selected_items = self.selectedItems()
        selected_item_num = len(selected_items)
        selected_groups = []
        selected_channels = []
        for selected_item in selected_items:
            if type(selected_item) == GroupItem:
                selected_groups.append(selected_item)
            elif type(selected_item) == ChannelItem:
                selected_channels.append(selected_item)

        self.selected_groups, self.selected_channels = selected_groups, selected_channels
        if selected_item_num == 0:  # nothing is selected
            self.selection_state = nothing_selected
        elif len(selected_channels) == 1 and len(selected_groups) == 0:  # just one channel
            self.selection_state = channel_selected
        elif len(selected_channels) > 1 and len(selected_groups) == 0:  # multiple channels and no group
            self.selection_state = channels_selected
        elif len(selected_channels) == 0 and len(selected_groups) == 1:  # just one group
            self.selection_state = group_selected
        elif len(selected_channels) == 0 and len(selected_groups) > 1:  # multiple groups and no channel
            self.selection_state = groups_selected
        elif len(selected_channels) > 0 and len(selected_groups) > 0:  # channel(s) and group(s)
            self.selection_state = mix_selected
        else:
            print(": ) What are you doing???")

        self.selection_changed_signal.emit("Selection Changed")
        print("Selection Changed")

    # @QtCore.pyqtSlot()
    def item_changed(self, item, column):  # check box on change
        # print(item.data(0, 0))
        # if hasattr(item, 'attribute')::
        # print(item.data(0,0))
        # if hasattr(item, 'item_type') and item.item_type == 'group':
        #     self.item_changed_signal.emit('Item changed')
        # print(item.data(0,0))
        # if item.checkState(column) == Qt.Checked or item.checkState(column) == Qt.PartiallyChecked:
        #     item.setForeground(0, QBrush(QColor(color_green)))
        #     item.display = 1
        # else:
        #     item.setForeground(0, QBrush(QColor(color_white)))
        #     item.display = 0
        # if hasattr(item, 'item_type') and item.item_type == 'group':
        # print('John')
        print(item.data(0,0))
        ## the color change due to the checkbox also induce a item_change signal

        if type(item) == GroupItem:
            self.update_info_box_signal.emit('Item changed')
        if type(item) == ChannelItem:
            checked = item.checkState(column) == QtCore.Qt.Checked
            parent_group = item.parent().data(0, 0)
            self.channel_is_display_changed_signal.emit((int(item.lsl_index), parent_group, checked))

    # print(item.data(0, 0))

    def create_new_group(self, new_group_name):
        group_names = self.get_group_names()
        selected_items = self.selectedItems()
        # new_group_name = self.newGroupNameTextbox.text()

        if new_group_name:
            if len(selected_items) == 0:
                dialog_popup('please select at least one channel to create a group')
            elif new_group_name in group_names:
                dialog_popup('Cannot Have duplicated Group Names')
                return
            else:
                for selected_item in selected_items:
                    if type(selected_item) == GroupItem:
                        dialog_popup('group item cannot be selected while creating new group')
                        return
                # create new group:

                # self.disconnect_selection_changed()
                self.clearSelection()

                new_group = self.add_group_item(parent_item=self.stream_root,
                                                group_name=new_group_name,
                                                display=any([item.display for item in selected_items]),
                                                plot_format='time_series')
                for selected_item in selected_items:
                    self.change_parent(item=selected_item, new_parent=new_group)

                # self.reconnect_selection_changed()

            self.remove_empty_groups()
            self.expandAll()
        else:
            dialog_popup('please enter your group name first')
            return

    def disconnect_selection_changed(self):
        self.selectionModel().selectionChanged.disconnect(self.selection_changed)

    def reconnect_selection_changed(self):
        self.selectionModel().selectionChanged.connect(self.selection_changed)
        self.selection_changed()
