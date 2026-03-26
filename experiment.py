# -*- coding: utf-8 -*-

__author__ = 'Brett Feltmate'
import os
from csv import DictWriter

import klibs
from klibs import P

from natnetclient_rough import NatNetClient  # type: ignore[import]
from OptiTracker import OptiTracker  # type: ignore[import]
from pyfirmata import serial  # type: ignore[import]

# colour fills
WHITE = (255, 255, 255, 255)
GRUE = (90, 90, 96, 255)
RED = (255, 0, 0, 255)
BLUE = (0, 0, 255, 255)
GREEN = (0, 255, 0, 255)
PURP = (255, 0, 255, 255)

# anti-typo protections
LEFT = 'left'
RIGHT = 'right'
WIDE = 'wide'
TALL = 'tall'
TARGET = 'target'
DISTRACTOR = 'distractor'
GBYK = 'GBYK'
KBYG = 'KBYG'
GO_SIGNAL = 'go_signal'
REACH_WINDOW_CLOSED = 'reach_window_closed'
TRIAL_TIMEOUT = 'trial_timeout'
POS_X = 'pos_x'
POS_Y = 'pos_y'
POS_Z = 'pos_z'
SPACE = 'space'
PREMATURE_REACH = 'Premature reach'
REACH_TIMEOUT = 'Reach timeout'
NA = 'NA'
P1 = 'p1'
P2 = 'p2'


class GraspVsPoint_BrettMSc(klibs.Experiment):
    def setup(self):
        # manages stream
        self.nnc = NatNetClient()
        self.nnc.markers_listener = self.marker_set_listener

        # middleman between natnet stream and experiment
        self.ot = OptiTracker(marker_count=10, sample_rate=120, window_size=5)

        # plato goggles controller
        self.goggles = serial.Serial(port=P.arduino_comport, baudrate=P.baudrate)  # type: ignore[known-attribute]

        # sizings
        self.px_cm = int(P.ppi / 2.54)

        self.locs = {
            LEFT: (P.sc)
        }

    def block(self):
        pass

    def trial_prep(self):
        pass

    def trial(self):

        return {'block_num': P.block_number, 'trial_num': P.trial_number}

    def trial_clean_up(self):
        pass

    def clean_up(self):
        pass

    def marker_set_listener(self, marker_set: dict) -> None:
        """Write marker set data to CSV file.

        Args:
            marker_set (dict): Dictionary containing marker data to be written.
                Expected format: {'markers': [{'key1': val1, ...}, ...]}
        """

        if marker_set.get('label') == P.hand_marker_setname:  # type: ignore[known-attribute]
            # Append data to trial-specific CSV file
            fname = self.ot.data_dir
            header = list(marker_set['markers'][0].keys())

            # if file doesn't exist, create it and write header
            if not os.path.exists(fname):
                with open(fname, 'w', newline='') as file:
                    writer = DictWriter(file, fieldnames=header)
                    writer.writeheader()

            # append marker data to file
            with open(fname, 'a', newline='') as file:
                writer = DictWriter(file, fieldnames=header)
                for marker in marker_set.get('markers', None):  # type: ignore[iterable]
                    if marker is not None:
                        writer.writerow(marker)
