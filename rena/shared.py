# replay
from enum import Enum

FAIL_INFO = 'fail!'
START_COMMAND = 'start!'
START_SUCCESS_INFO = 'start'
VIRTUAL_CLOCK_REQUEST = 'v'

PLAY_PAUSE_COMMAND = 'pp'
PLAY_PAUSE_SUCCESS_INFO = 'pp!'

STOP_COMMAND = 'stop!'
STOP_SUCCESS_INFO = 'stop'

TERMINATE_COMMAND = 't!'
TERMINATE_SUCCESS_COMMAND = 't'

# scripting
SCRIPT_STDOUT_MSG_PREFIX = 'S!'
SCRIPT_STOP_REQUEST = 'stop'
SCRIPT_STOP_SUCCESS = 'stopsuccess'
SCRIPT_INFO_REQUEST = 'i'
DATA_BUFFER_PREFIX = 'd'.encode('utf-8')
SCRIPT_PARAM_CHANGE = 'p'

try:
    rena_base_script = open("scripting/BaseRenaScript.py", "r").read()
except FileNotFoundError:
    rena_base_script = open("../scripting/BaseRenaScript.py", "r").read()

class ParamChange(Enum):
    ADD = 'a'
    REMOVE = 'r'
    CHANGE = 'c'
