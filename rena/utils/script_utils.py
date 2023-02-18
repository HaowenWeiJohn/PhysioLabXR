import importlib.util
import os.path
import os
import pickle
import sys
from inspect import isclass
from exceptions.exceptions import InvalidScriptPathError, ScriptSyntaxError, ScriptMissingModuleError

from multiprocessing import Process

from rena import config
from rena.scripting.RenaScript import RenaScript
from rena.shared import SCRIPT_STOP_REQUEST

debugging = False

def start_script_server(script_path, script_args):
    print("script process, starting script thread")
    # sys.stdout = Stream(newText=self.on_print)

    target_class = get_target_class(script_path)
    replay_client_thread = target_class(**script_args)
    replay_client_thread.start()

def validate_script_path(script_path: str):
    """
    Validate if the script at <script_path> can be loaded without any import
    or module not found error.
    Also checks to make sure if the first class of in the script is an implementation
    of the RenaScript class.
    This function ensures that of the script can be laoded. Then it will run under
    the scripting widget
    :param script_path: path to the script to be loaded
    """
    try:
        assert os.path.exists(script_path)
    except AssertionError:
        raise InvalidScriptPathError(script_path, 'File Not Found')
    try:
        assert script_path.endswith('.py')
    except AssertionError:
        raise InvalidScriptPathError(script_path, 'File name must end with .py')
    try:
        target_class = get_target_class(script_path)
        target_class_name = get_target_class_name(script_path)
    except IndexError:
        raise InvalidScriptPathError(script_path, 'Script does not have class defined')
    except ModuleNotFoundError as e:
        raise ScriptMissingModuleError(script_path, e)
    except SyntaxError as e:
        raise ScriptSyntaxError(e)
    try:
        assert issubclass(target_class, RenaScript)
    except AssertionError:
        raise InvalidScriptPathError(script_path, 'The first class ({0}) in the script does not inherit RenaScript. '.format(target_class_name))


def get_target_class(script_path):
    spec = importlib.util.spec_from_file_location(os.path.basename(os.path.normpath(script_path)), script_path)
    script_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script_module)

    classes = [x for x in dir(script_module) if
               isclass(getattr(script_module, x))]  # all the classes defined in the module
    classes = [script_module.__getattribute__(x) for x in classes if x != 'RenaScript']  # exclude RenaScript itself
    classes = [x for x in classes if issubclass(x, RenaScript)]
    try:
        assert len(classes) == 1
    except AssertionError:
        raise InvalidScriptPathError(script_path, 'Script has more than one classes that extends RenaScript. There can be only one subclass of RenaScript in the script file.')
    return classes[0]


def get_target_class_name(script_path):
    spec = importlib.util.spec_from_file_location(os.path.basename(os.path.normpath(script_path)), script_path)
    script_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script_module)
    classes = [x for x in dir(script_module) if
               isclass(getattr(script_module, x))]  # all the classes defined in the module
    # script_args = {'inputs': None, 'input_shapes': None,
    #                'outputs': None, 'output_num_channels': None,
    #                'params': None, 'port': None, 'run_frequency': None,
    #                'time_window': None}
    classes = [x for x in classes if x != 'RenaScript' ]
    return classes[0]


def start_script(script_path, script_args):
    print('Script started')
    if not debugging:
        script_process = Process(target=start_script_server, args=(script_path, script_args))
        script_process.start()
        return script_process
    else:
        pickle.dump([script_path, script_args], open('start_script_args.p', 'wb'))


if __name__ == '__main__':
    """
    Running this script is for debugging
    """
    # script_args = {'inputs': None, 'input_shapes': None,
    #                'outputs': None, 'output_num_channels': None,
    #                'params': None, 'port': None, 'run_frequency': None,
    #                'time_window': None}
    # script_path = '../scripting/IndexPen.py'
    script_path, script_args = pickle.load(open('start_script_args.p', 'rb'))
    start_script_server(script_path, script_args)