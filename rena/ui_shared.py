from PyQt5.QtCore import QSize
from PyQt5.QtGui import QIcon, QPixmap

from rena.config_ui import stream_widget_icon_size

start_stream_icon = QIcon('../media/icons/start.svg')
stop_stream_icon = QIcon('../media/icons/stop.svg')
options_icon = QIcon('../media/icons/options.svg')
pop_window_icon = QIcon('../media/icons/popwindow.svg')
dock_window_icon = QIcon('../media/icons/dockwindow.svg')
remove_stream_icon = QIcon('../media/icons/removestream.svg')


pause_icon = QIcon('../media/icons/pause.svg')

# Stream widget icon in the visualization tab
stream_unavailable_icon = QIcon('../media/icons/streamwidget_stream_unavailable.svg')
# stream_unavailable_pixmap = stream_unavailable_icon.pixmap(72, 72)
stream_available_icon = QIcon('../media/icons/streamwidget_stream_available.svg')
# stream_available_pixmap = stream_available_icon.pixmap(72, 72)
stream_active_icon = QIcon('../media/icons/streamwidget_stream_viz_active.svg')
# stream_active_pixmap = stream_active_icon.pixmap(72, 72)


# stream_unavailable_pixmap = QPixmap('../media/icons/streamwidget_stream_unavailable.png')
# stream_available_pixmap = QPixmap('../media/icons/streamwidget_stream_available.png')
# stream_active_pixmap = QPixmap('../media/icons/streamwidget_stream_viz_active.png')

# strings in Rena
recording_tab_file_save_label_prefix = 'File will be saved as: '
start_recording_text = 'Start Recording'
stop_recording_text = 'Stop Recording'
