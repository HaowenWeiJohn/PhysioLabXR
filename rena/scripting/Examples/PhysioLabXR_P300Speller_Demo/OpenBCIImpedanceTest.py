from pyOpenBCI import OpenBCICyton

def handle_sample(sample):
    print(sample.channels_data)  # Print the EEG data

# Replace 'COM3' with the actual serial port of your Cyton board
board = OpenBCICyton(port='COM4')

# Start streaming data and call the 'handle_sample' function for each sample
board.start_stream(handle_sample)
board.stop_stream()


# import threading
# import time
# from pyOpenBCI import OpenBCICyton
#
# # Define a global variable to store the latest sample
# latest_sample = None
#
# def handle_sample(sample):
#     global latest_sample
#     latest_sample = sample.channels_data
#
# def data_reader():
#     # Replace 'COM4' with the actual serial port of your Cyton board
#     board = OpenBCICyton(port='COM4')
#     board.start_stream(handle_sample)
#
# # Start the data reader in a separate thread
# data_thread = threading.Thread(target=data_reader, daemon=True)
# data_thread.start()
#
# # Main loop to process data
# while True:
#     if latest_sample is not None:
#         print("Latest EEG data:", latest_sample)
#     time.sleep(1)  # Adjust the interval as needed

