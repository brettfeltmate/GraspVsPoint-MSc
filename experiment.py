# -*- coding: utf-8 -*-

__author__ = 'Brett Feltmate'
import os
from csv import DictWriter

import klibs
from klibs import P
from klibs.KLBoundary import CircleBoundary, BoundarySet
from klibs.KLExceptions import TrialException
from klibs.KLGraphics import KLDraw as kld
from klibs.KLGraphics import fill, blit, flip, clear
from klibs.KLConstants import STROKE_INNER
from klibs.KLUserInterface import (
    key_pressed,
    smart_sleep,
    mouse_pos,
    pump,
    ui_request,
)
from klibs.KLUtilities import line_segment_len
from klibs.KLAudio import Tone
from klibs.KLCommunication import message
from sdl2.ext import get_key_state

from natnetclient_rough import NatNetClient  # type: ignore[import]
from OptiTracker import OptiTracker  # type: ignore[import]
from pyfirmata import serial  # type: ignore[import]

from random import randrange

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
TARGET = 'target'
DISTRACTOR = 'distractor'
GBYK = 'GBYK'
KBYG = 'KBYG'
GO_SIGNAL = 'go_signal'
REACTION_TIMEOUT = 'reaction_timeout'
REACH_TIMEOUT = 'reach_timeout'
TRIAL_TIMEOUT = 'trial_timeout'
POS_X = 'pos_x'
POS_Y = 'pos_y'
POS_Z = 'pos_z'
SPACE = 'space'
PREMATURE_REACH = 'Premature reach'
PREMATURE_STOP = 'Premature stop'
NA = 'NA'
CRADLE = 'cradle'
READY = 'ready'
TASK = 'task'
ACTION = 'action'
HAND = 'hand'
PRE_GO = 'pre_go'
PRE_REACH_START = 'pre_reach_start'
PRE_REVEAL = 'pre_reveal'
PRE_REACH_END = 'pre_reach_end'
REACH_END = 'reach_end'
CURSOR = 'cursor'


class GraspVsPoint_BrettMSc(klibs.Experiment):
    def setup(self):
        # manages stream
        self.nnc = NatNetClient()
        self.nnc.markers_listener = self.marker_set_listener

        # middleman between natnet stream and experiment
        self.ot = OptiTracker(marker_count=10, sample_rate=120, window_size=5)

        # plato goggles controller
        self.goggles = serial.Serial(
            port=P.arduino_comport,  # type: ignore[known-attribute]
            baudrate=P.baudrate,  # type: ignore[known-attribute]
            open_cmd=P.plato_open_cmd,  # type: ignore[known-attribute]
            close_cmd=P.plato_close_cmd,  # type: ignore[known-attribute]
        )

        self.go_signal = Tone(
            P.tone_duration, P.tone_shape, P.tone_freq, P.tone_volume  # type: ignore[known-attribute]
        )

        # sizings
        self.px_cm = int(P.ppi / 2.54)

        self.locs = {
            LEFT: (P.screen_c[0] - (P.cm_placeholder_offset * self.px_cm), P.screen_c[1]),  # type: ignore[known-attribute]
            RIGHT: (P.screen_c[0] + (P.cm_placeholder_offset * self.px_cm), P.screen_c[1]),  # type: ignore[known-attribute]
            READY: (P.screen_c[0], 0),
        }

        target_stroke = [self.cm_brim * self.px_cm, WHITE, STROKE_INNER]  # type: ignore[known-attribute]
        nontarget_stroke = [self.cm_brim * self.px_cm, GRUE, STROKE_INNER]  # type: ignore[known-attribute]

        self.placholders = {
            TARGET: kld.Annulus(
                diameter=P.cm_diam * self.px_cm,  # type: ignore[known-attribute]
                thickness=self.px_cm // 5,
                stroke=target_stroke,
                fill=GRUE,
            ),
            DISTRACTOR: kld.Annulus(
                diameter=P.cm_diam * self.px_cm,  # type: ignore[known-attribute]
                thickness=self.px_cm // 5,
                stroke=nontarget_stroke,
                fill=GRUE,
            ),
            READY: kld.Annulus(
                diameter=P.cm_diam * self.px_cm,  # type: ignore[known-attribute]
                thickness=self.px_cm // 5,
                stroke=nontarget_stroke,
                fill=GREEN,
            ),
            CURSOR: kld.Annulus(
                diameter=P.cm_diam * self.px_cm,  # type: ignore[known-attribute]
                thickness=self.px_cm // 5,
                stroke=nontarget_stroke,
                fill=PURP,
            ),
        }

        self.conditions = [
            (task, action, hand)
            for task in P.task_order  # type: ignore[known-attribute]
            for action in P.action_order  # type: ignore[known-attribute]
            for hand in P.hand_order  # type: ignore[known-attribute]
        ]

        self.messages = {
            PREMATURE_REACH: 'Wait for the tone to start your reach!',
            REACTION_TIMEOUT: 'Try to react faster to the tone!',
            REACH_TIMEOUT: 'Try to reach the target faster',
            PREMATURE_STOP: 'Try not to pause or hesistate mid-reach!',
        }

        if P.run_practice_blocks:
            self.insert_practice_block(
                block_nums=[1, 4], trial_counts=P.trials_per_practice_block  # type: ignore[known-attribute]
            )

            self.conditions = (
                [self.conditions[0]]
                + [self.conditions[:4]]
                + [self.conditions[3]]
                + [self.conditions[4:]]
            )

        # make participant folder with testing and practice subfolders
        self.participant_dir = os.path.join(P.data_dir, f'P{P.participant_id}')  # type: ignore[known-attribute]
        self.practice_dir = os.path.join(self.participant_dir, 'practice')
        self.testing_dir = os.path.join(self.participant_dir, 'testing')

    def block(self):
        mouse_pos(position=[0, 0])

        self.current = {
            TASK: self.conditions[P.block_number - 1][0],  # type: ignore[known-attribute]
            ACTION: self.conditions[P.block_number - 1][1],  # type: ignore[known-attribute]
            HAND: self.conditions[P.block_number - 1][2],  # type: ignore[known-attribute]
        }

        y_offset = 0 if self.current[ACTION] == 'point' else P.cm_wiggle_room * self.px_cm  # type: ignore[known-attribute]

        self.bounds = BoundarySet(
            [
                CircleBoundary(label=LEFT, center=[self.locs[LEFT][0], self.locs[LEFT][1] + y_offset], radius=P.cm_wiggle_room * self.px_cm),  # type: ignore[known-attribute]
                CircleBoundary(label=RIGHT, center=[self.locs[RIGHT][0], self.locs[RIGHT][1] + y_offset], radius=P.cm_wiggle_room * self.px_cm),  # type: ignore[known-attribute]
                CircleBoundary(label=READY, center=self.locs[READY], radius=P.cm_wiggle_room * self.px_cm),  # type: ignore[known-attribute]
            ]
        )

        instrux = f'In this block, you will be asked to {self.current[ACTION]} at a target item with your {self.current[HAND]} hand.\n'  # type: ignore[known-attribute]

        instrux += '\nTrials will begin with the goggles opening. Then a tone will be played, try to begin reaching as soon as you hear it!.\n'

        if self.current[TASK] == GBYK:
            instrux += '\nWhich item is your target will be revealed after you start reaching, indicated by a white ring underneath it.\n'
        else:
            instrux += '\nYour target will be indicated at the start, by a white ring underneath it.\n'

        instrux += '\nIf you pause or hesistate mid-reach, the trial will be aborted, so try to complete your reach in one smooth motion!\n'

        instrux += '\nAt the end you will be instructed to press and HOLD spacebar until the next trial begins. The goggles will close once you do.\n'

        instrux += '\n\nPress and hold spacebar when you are ready to begin!'

        fill()
        blit(self.placholders[READY], registration=5, location=self.locs[READY])  # type: ignore[known-attribute]
        message(text=instrux, location=P.screen_c, wrap_width=P.screen_x * 0.8)  # type: ignore[operator]
        flip()

        while True:
            q = pump(True)
            ui_request(queue=q)
            if get_key_state(SPACE) and self.bounds.within_boundary(
                READY, mouse_pos()
            ):
                break

    def trial_prep(self):
        mouse_pos(position=[0, 0])

        # when to label a reach as being in-progress
        self.reach_threshold = randrange(*P.cm_reach_start_threshold) * self.px_cm  # type: ignore[known-attribute]

        # event timings
        self.evm.add_event(
            label=GO_SIGNAL, onset=randrange(*P.ms_go_signal_onset_interval)  # type: ignore[known-attribute]
        )

        self.evm.add_event(
            label=REACTION_TIMEOUT,
            onset=P.ms_window_to_react,  # type: ignore[known-attribute]
            after=GO_SIGNAL,
        )

        # determine targ/dist locations
        self.distractor_loc = LEFT if self.target_loc == RIGHT else RIGHT  # type: ignore[known-attribute]

        trial_file = f'Block_{P.block_number}_Task_{self.current[TASK]}_ Hand_{self.current[HAND]}_Action_{self.current[ACTION]}_Trial_{P.trial_number}_TargetLoc_{self.target_loc}.csv'  # type: ignore[known-attribute][x]

        self.ot.data_dir = os.path.join(
            self.practice_dir if P.practicing else self.testing_dir, trial_file
        )

        # blind participant during prop setup
        self.goggles.write(P.plato_close_cmd)  # type: ignore[known-attribute]

        self.present_stimuli(prep=True)

        trial_ready = False
        participant_ready = False

        pump()

        while not trial_ready or not participant_ready:
            if not trial_ready:
                trial_ready = self.bounds.within_boundary(READY, mouse_pos())

            if not participant_ready:
                participant_ready = key_pressed(key=SPACE)

        self.present_stimuli(mark_target=self.current[TASK] == KBYG)

        self.nnc.startup()  # start marker tracking

        # ensure some data exists before beginning trial
        smart_sleep(P.opti_trial_lead_time)  # type: ignore[known-attribute]

    def trial(self):

        self.goggles.open()

        # used later for triggering target reveal during GBYK trials
        starting_pos = self.get_adj_hand_pos()

        while self.evm.before(GO_SIGNAL):
            if get_key_state(SPACE) == 0:
                self.abort_trial_premature_stoppage(reason=PREMATURE_REACH)
                raise TrialException(PREMATURE_REACH)

        self.go_signal.play()
        rt_window_start = self.evm.trial_time_ms
        rt = None

        self.evm.add_event(
            label=REACTION_TIMEOUT,
            onset=self.evm.trial_time_ms + P.ms_window_to_react,  # type: ignore[known-attribute]
        )

        started_reach = False

        while self.evm.before(REACTION_TIMEOUT) and not started_reach:
            if get_key_state(SPACE) == 0:
                started_reach = True
                rt = self.evm.trial_time_ms - rt_window_start

        if not started_reach:
            self.abort_trial_premature_stoppage(reason=REACTION_TIMEOUT)
            raise TrialException(REACTION_TIMEOUT)

        mt_window_start = self.evm.trial_time_ms

        self.evm.add_event(
            label=REACH_TIMEOUT,
            onset=self.evm.trial_time_ms + P.ms_window_to_reach,  # type: ignore[known-attribute]
        )

        reach_made = False
        reach_item = None
        mark_target = self.current[TASK] == KBYG

        while not reach_made and self.evm.before(REACH_TIMEOUT):
            self.present_stimuli(mark_target=mark_target)

            hand_pos = self.get_adj_hand_pos()

            if not mark_target:
                mark_target = (
                    line_segment_len(starting_pos, hand_pos)
                    > self.reach_threshold
                )

            if mark_target:
                if self.bounds.within_boundary(TARGET, hand_pos):
                    reach_made = True
                    reach_item = TARGET
                elif self.bounds.within_boundary(DISTRACTOR, hand_pos):
                    reach_made = True
                    reach_item = DISTRACTOR

        if not reach_item:
            self.abort_trial_premature_stoppage(reason=REACH_TIMEOUT)
            if not mark_target:
                raise TrialException(REACH_TIMEOUT)
        else:
            mt = self.evm.trial_time_ms - mt_window_start

        self.evm.add_event(
            label=TRIAL_TIMEOUT,
            onset=self.evm.trial_time_ms + P.ms_post_reach_window,  # type: ignore[known-attribute]
        )

        while self.evm.before(TRIAL_TIMEOUT):
            q = pump(True)
            ui_request(queue=q)

        self.nnc.shutdown()  # stop marker tracking

        return {
            'block_num': P.block_number,
            'trial_num': P.trial_number,
            'task': self.current[TASK],
            'action': self.current[ACTION],
            'hand': self.current[HAND],
            'target_loc': self.target_loc,  # type: ignore[known-attribute]
            'reaction_time': rt if rt else NA,
            'movement_time': mt if mt else NA,
            'reach_item': reach_item if reach_item else NA,
        }

    def trial_clean_up(self):
        clear()
        message('Press and hold spacebar', location=P.screen_c)
        flip()

        while True:
            q = pump(True)
            ui_request(queue=q)
            if key_pressed(key=SPACE):
                break

        self.goggles.close()

    def clean_up(self):
        pass

    def abort_trial_premature_stoppage(self, reason: str):
        self.nnc.shutdown()  # stop marker tracking

        fill()
        message(
            text=self.messages.get(reason, 'Trial aborted!'),
            location=P.screen_c,
        )
        flip()

        smart_sleep(1000)

    def present_stimuli(self, prep=False, mark_target=False):
        fill()

        if P.development_mode:
            blit(
                self.placholders[CURSOR],
                registration=5,
                location=self.get_adj_hand_pos(),
            )

        if prep:
            message(
                'Press READY to start. Ensure spacebar is held down.',
                location=[P.screen_c[0], P.screen_c[1] // 3],  # type: ignore[unsupported-operator]
            )
            blit(
                self.placholders[READY],
                registration=5,
                location=self.locs[READY],
            )

        self.placeholders[TARGET].fill = WHITE if mark_target else GRUE  # type: ignore[known-attribute]

        blit(
            self.placholders[TARGET],
            registration=5,
            location=self.locs[self.target_loc],  # type: ignore[known-attribute]
        )

        blit(
            self.placholders[DISTRACTOR],
            registration=5,
            location=self.locs[self.distractor_loc],
        )

        flip()

    def get_adj_hand_pos(self):
        markers = self.ot.position()
        hand_pos = {
            axis: markers[axis][0].item() * self.px_cm
            for axis in (POS_X, POS_Y, POS_Z)
        }
        return self.translate_pos(hand_pos)

    def translate_pos(self, pos):
        return (P.screen_x - pos[POS_X], P.screen_y - pos[POS_Z])

    def marker_set_listener(self, marker_set: dict) -> None:
        """Write marker set data to CSV file.

        Args:
            marker_set (dict): Dictionary containing marker data to be written.
                Expected format: {'markers': [{'key1': val1, ...}, ...]}
        """

        if marker_set.get('label') == self.current[HAND]:  # type: ignore[known-attribute]
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


class PlatoGoggles:
    def __init__(
        self, comport: str, baudrate: int, open_cmd: bytes, close_cmd: bytes
    ):
        self.serial_conn = serial.Serial(port=comport, baudrate=baudrate)
        self.open_bytecmd = open_cmd
        self.close_bytecmd = close_cmd

    def open(self):
        self.serial_conn.write(self.open_bytecmd)

    def close(self):
        self.serial_conn.write(self.close_bytecmd)
