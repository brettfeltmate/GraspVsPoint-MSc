### Klibs Parameter overrides ###

#########################################
# Runtime Settings
#########################################
collect_demographics = True
manual_demographics_collection = False
manual_trial_generation = False
run_practice_blocks = True
multi_user = False
view_distance = (
    57  # in centimeters, 57cm = 1 deg of visual angle per cm of screen
)
allow_hidpi = True

#########################################
# Available Hardware
#########################################
eye_tracker_available = False
eye_tracking = False

#########################################
# Environment Aesthetic Defaults
#########################################
default_fill_color = (45, 45, 45, 255)
default_color = (255, 255, 255, 255)
default_font_size = 23
default_font_unit = 'px'
default_font_name = 'Hind-Medium'

#########################################
# EyeLink Settings
#########################################
manual_eyelink_setup = False
manual_eyelink_recording = False

saccadic_velocity_threshold = 20
saccadic_acceleration_threshold = 5000
saccadic_motion_threshold = 0.15

#########################################
# Experiment Structure
#########################################
multi_session_project = False
trials_per_block = 40
blocks_per_experiment = 6
conditions = []
default_condition = None

#########################################
# Development Mode Settings
#########################################
dm_auto_threshold = True
dm_trial_show_mouse = True
dm_ignore_local_overrides = False
dm_show_gaze_dot = True

#########################################
# Data Export Settings
#########################################
primary_table = 'trials'
unique_identifier = 'userhash'
exclude_data_cols = ['created']
append_info_cols = ['random_seed']
datafile_ext = '.tsv'
append_hostname = False

#########################################
# PROJECT-SPECIFIC VARS
#########################################
task_order = ['gbyk', 'kbyg']
hand_order = ['right', 'left']
action_order = ['point', 'grasp']
trials_per_practice_block = 10

cm_diam = 6
cm_brim = 1
cm_placeholder_offset = 20
cm_handstand_offset = 40
cm_wiggle_room = 5
cm_reach_start_threshold = (10, 15, 1)   # min, max, step

ms_go_signal_onset_interval = (100, 1600, 200)  # min, max, step
ms_window_to_react = 500
ms_window_to_reach = 500
ms_post_reach_window = 500

# audio
tone_duration = 100
tone_shape = 'sine'
tone_freq = 784  # ridin' on yo G5 airplane
tone_volume = 1.0

opti_data_dir = 'OptiData'
opti_trial_lead_time = 60   # ms

plato_open_cmd = b'55'
plato_close_cmd = b'56'
arduino_comport = 'COM6'
baudrate = 9600
hand_marker_setnames = ['right', 'left']
opti_marker_count = 10
opti_samplerate = 120
opti_window_size = 5
