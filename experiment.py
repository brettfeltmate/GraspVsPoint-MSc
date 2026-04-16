# -*- coding: utf-8 -*-
# pyright: reportAttributeAccessIssue = false

__author__ = 'Brett Feltmate'

import os
from csv import DictWriter
from random import randrange
from pyfirmata import serial

# experiment framework and utilities
import klibs
from klibs import P
from klibs.KLBoundary import CircleBoundary, BoundarySet
from klibs.KLExceptions import TrialException
from klibs.KLGraphics import KLDraw as kld
from klibs.KLGraphics import fill, blit, flip, clear
from klibs.KLConstants import STROKE_CENTER
from klibs.KLUserInterface import (
    key_pressed,
    smart_sleep,
    mouse_pos,
    pump,
    ui_request,
    any_key
)
from klibs.KLUtilities import line_segment_len
from klibs.KLAudio import Tone
from klibs.KLCommunication import message

# defined in ExpAssets/Resources/code
from OptiTracker import OptiTracker  # pyright: ignore[reportMissingImports]
from natnetclient_rough import (  # pyright: ignore[reportMissingImports]
    NatNetClient,
)
from get_key_state import (  # pyright: ignore[reportMissingImports]
    get_key_state,
)


# fills
WHITE = (255, 255, 255, 255)
GRAY = (120, 120, 120, 255)
RED = (255, 0, 0, 255)
BLUE = (0, 0, 255, 255)
GREEN = (0, 255, 0, 255)
PURP = (255, 0, 255, 255)

# anti-typo protections
LEFT = 'left'
RIGHT = 'right'
TARGET = 'target'
NONTARGET = 'nontarget'
BOUNDARY = 'boundary'
GBYK = 'gbyk'
KBYG = 'kbyg'
GO_SIGNAL = 'go_signal'
REACTION_TIMEOUT = 'reaction_timeout'
REACH_TIMEOUT = 'reach_timeout'
TRIAL_TIMEOUT = 'trial_timeout'
POS_X = 'pos_x'
POS_Y = 'pos_y'
POS_Z = 'pos_z'
SPACE = 'space'
PREMATURE_REACH = 'Premature reach'
PRACTICE = 'practice'
TESTING = 'testing'
PREMATURE_STOP = 'Premature stop'
NA = 'NA'
CRADLE = 'cradle'
READY = 'ready'
TASK = 'task'
ACTION = 'action'
HAND = 'hand'
POINT = 'point'
GRASP = 'grasp'
PRE_GO = 'pre_go'
PRE_REACH_START = 'pre_reach_start'
PRE_REVEAL = 'pre_reveal'
PRE_REACH_END = 'pre_reach_end'
REACH_END = 'reach_end'
CURSOR = 'cursor'


class GraspVsPoint_BrettMSc(klibs.Experiment):
    def setup(self):
        # utilities for parsing and manipulating mocap data stream
        self.nnc = NatNetClient()
        self.nnc.markers_listener = self.marker_set_listener
        self.ot = OptiTracker(
            # P for ExpAssets/Config/GraspVsPoint_BrettMSc_params.py
            marker_count=P.opti_marker_count,
            sample_rate=P.opti_sample_rate,
            window_size=P.opti_window_size,
        )

        # plato goggles controller
        # class defined below experiment class def
        self.goggles = PlatoGoggles(
            comport=P.arduino_comport,
            baudrate=P.baudrate,
            open_cmd=P.plato_open_cmd,
            close_cmd=P.plato_close_cmd,
        )

        self.go_signal = Tone(
            P.tone_duration,
            P.tone_shape,
            P.tone_freq,
            P.tone_volume,
        )

        self.px_cm = int(P.ppi / 2.54)

        self.locs = {
            LEFT: (
                P.screen_c[0] - (P.cm_placeholder_offset * self.px_cm),
                P.screen_c[1] // 2,  # pyright: ignore[reportOperatorIssue]
            ),
            RIGHT: (
                P.screen_c[0] + (P.cm_placeholder_offset * self.px_cm),
                P.screen_c[1] // 2,  # pyright: ignore[reportOperatorIssue]
            ),
            READY: (P.screen_c[0], 0),
        }

        strokes = {
            TARGET: [P.cm_brim * self.px_cm, WHITE, STROKE_CENTER],
            NONTARGET: [P.cm_brim * self.px_cm, GRAY, STROKE_CENTER],
            READY: [P.cm_brim * self.px_cm, GREEN, STROKE_CENTER],
            CURSOR: [P.cm_brim * self.px_cm, PURP, STROKE_CENTER],
        }
        fills = {
            TARGET: WHITE,
            NONTARGET: GRAY,
            READY: GREEN,
            CURSOR: PURP,
        }

        self.stimuli = {
            label: kld.Annulus(
                diameter=P.cm_diam * self.px_cm,
                thickness=self.px_cm // 5,
                stroke=strokes[label],
                fill=fills[label],
            )
            for label in (TARGET, NONTARGET, READY, CURSOR)
        }

        self.conditions = [
            (task, action, hand)
            for task in P.task_order
            for action in P.action_order
            for hand in P.hand_order
        ]

        self.messages = {
            PREMATURE_REACH: 'Wait for the tone to start your reach!',
            REACTION_TIMEOUT: 'Try to react faster to the tone!',
            REACH_TIMEOUT: 'Try to reach the target faster',
            PREMATURE_STOP: 'Try not to pause or hesistate mid-reach!',
        }

        # repeat first block for practice
        if P.run_practice_blocks and not P.development_mode:
            self.insert_practice_block(
                block_nums=[1],
                trial_counts=P.trials_per_practice_block,
            )

            self.conditions.insert(0, self.conditions[0])

        # for storing mocap data during trial
        self.participant_dir = os.path.join(
            P.opti_data_dir, f'P{P.participant_id}'
        )
        os.makedirs(self.participant_dir, exist_ok=True)

        self.testing_dir = os.path.join(self.participant_dir, TESTING)
        os.makedirs(self.testing_dir, exist_ok=True)

        self.practice_dir = os.path.join(self.participant_dir, PRACTICE)
        os.makedirs(self.practice_dir, exist_ok=True)

    def block(self):
        # ensure isn't in ready area
        mouse_pos(position=[0, 0])
        self.goggles.open()

        self.condition = {
            TASK: self.conditions[P.block_number - 1][0],
            ACTION: self.conditions[P.block_number - 1][1],
            HAND: self.conditions[P.block_number - 1][2],
        }

        self.bounds = BoundarySet(
            [
                CircleBoundary(
                    label=READY,
                    center=self.locs[READY],
                    radius=P.cm_wiggle_room * self.px_cm // 2,
                )
            ]
        )

        instrux = f'({PRACTICE if P.run_practice_blocks else TESTING}) Block {P.block_number} of {P.blocks_per_experiment}\n\n'

        instrux += f'Task: {self.condition[TASK]}\nAction: {self.condition[ACTION]}\nHand: {self.condition[HAND]}\n\n'

        if self.condition[HAND] != self.conditions[P.block_number - 2][2] and P.block_number != 1:
            instrux += 'SWAP MARKERS!\n\n'

        instrux += 'Press and hold spacebar when ready!'

        fill()
        blit(self.stimuli[READY], registration=5, location=self.locs[READY])
        message(
            text=instrux,
            location=P.screen_c,
            wrap_width=int(
                P.screen_x * 0.6  # pyright: ignore[reportOperatorIssue]
            ),
        )
        flip()

        # skipping text requires both participant and experimentor
        while True:
            q = pump(True)
            ui_request(queue=q)
            if get_key_state(SPACE) and self.bounds.within_boundary(
                READY, mouse_pos()
            ):
                break

        self.goggles.close()

    def trial_prep(self):
        # same
        mouse_pos(position=[0, 0])

        y_offset = 0

        # because where the hand ends differs between pointing and grasping
        # and markers being placed atop hand, skewing it when perpendicular to screen
        if self.condition[ACTION] == POINT:
            y_offset = P.cm_wiggle_room * self.px_cm

        self.bounds = BoundarySet(
            [
                CircleBoundary(
                    label=TARGET if self.target_loc == LEFT else NONTARGET,
                    center=[
                        self.locs[LEFT][0],
                        self.locs[LEFT][1] + y_offset
                        ],
                    radius=P.cm_wiggle_room * self.px_cm,
                ),
                CircleBoundary(
                    label=TARGET if self.target_loc == RIGHT else NONTARGET,
                    center=[
                        self.locs[RIGHT][0],
                        self.locs[RIGHT][1] + y_offset,
                    ],
                    radius=P.cm_wiggle_room * self.px_cm,
                ),
                CircleBoundary(
                    label=READY,
                    center=self.locs[READY],
                    radius=P.cm_wiggle_room * self.px_cm,
                ),
            ]
        )

        # ring = kld.Annulus(
        #         diameter=P.cm_wiggle_room * self.px_cm,
        #         thickness=self.px_cm // 5,
        #         stroke=[self.px_cm, GREEN, STROKE_CENTER],
        #         fill=GREEN,
        # )

        # fill()
        # blit(ring, location = [ self.locs[LEFT][0], self.locs[LEFT][1] + y_offset ], registration = 5)
        # blit(ring, location = [ self.locs[RIGHT][0], self.locs[RIGHT][1] + y_offset ], registration = 5)
        # flip()
        # any_key()
        # quit()
        # distance at which target is revealed (GBYK)
        self.reach_threshold = (
            randrange(*P.cm_reach_start_threshold) * self.px_cm
        )

        # the timing of these events are deterministic
        # remaining events are relative and set during trial()
        self.evm.add_event(
            label=GO_SIGNAL,
            onset=randrange(*P.ms_go_signal_onset_interval),
        )

        self.evm.add_event(
            label=REACTION_TIMEOUT,
            onset=P.ms_window_to_react,
            after=GO_SIGNAL,
        )

        # determine targ/dist locations
        self.distractor_loc = LEFT if self.target_loc == RIGHT else RIGHT

        # Construct trial filename with current parameters
        trial_file = (
            f'Block_{P.block_number}_'
            f'Task_{self.condition[TASK]}_'
            f'Hand_{self.condition[HAND]}_'
            f'Action_{self.condition[ACTION]}_'
            f'Trial_{P.trial_number}_'
            f'TargetLoc_{self.target_loc}.csv'
        )

        # Set data directory for this trial
        data_dir = self.practice_dir if P.practicing else self.testing_dir
        self.ot.data_dir = os.path.join(data_dir, trial_file)

        self.nnc.startup()  # start marker tracking

        # ensure some data exists before beginning trial
        smart_sleep(P.opti_trial_lead_time)

        # blind participant during prop setup
        self.goggles.close()

        self.present_stimuli(prep=True)

        trial_ready = False
        participant_ready = False

        pump()

        while not trial_ready or not participant_ready:
            if not trial_ready:
                trial_ready = self.bounds.within_boundary(READY, mouse_pos())

            if not participant_ready:
                participant_ready = key_pressed(key=SPACE)

        self.present_stimuli(mark_target=self.condition[TASK] == KBYG)

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
            onset=self.evm.trial_time_ms + P.ms_window_to_react,
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
        mt = None

        self.evm.add_event(
            label=REACH_TIMEOUT,
            onset=self.evm.trial_time_ms + P.ms_window_to_reach,
        )

        reached = False
        reached_item = None
        visible_target = self.condition[TASK] == KBYG

        while not reached and self.evm.before(REACH_TIMEOUT):
            self.present_stimuli(mark_target=visible_target)

            hand_pos = self.get_adj_hand_pos()

            if not visible_target:
                visible_target = (
                    line_segment_len(starting_pos, hand_pos)
                    > self.reach_threshold
                )

            if visible_target:
                if self.bounds.within_boundary(TARGET, hand_pos):
                    reached = True
                    reached_item = TARGET
                elif self.bounds.within_boundary(NONTARGET, hand_pos):
                    reached = True
                    reached_item = NONTARGET

        if not reached_item:
            self.abort_trial_premature_stoppage(reason=REACH_TIMEOUT)
            if not visible_target:
                raise TrialException(REACH_TIMEOUT)
        else:
            mt = self.evm.trial_time_ms - mt_window_start

        self.evm.add_event(
            label=TRIAL_TIMEOUT,
            onset=self.evm.trial_time_ms + P.ms_post_reach_window,
        )

        while self.evm.before(TRIAL_TIMEOUT):
            q = pump(True)
            ui_request(queue=q)

        self.nnc.shutdown()  # stop marker tracking

        return {
            'block_num': P.block_number,
            'trial_num': P.trial_number,
            'task': self.condition[TASK],
            'action': self.condition[ACTION],
            'hand': self.condition[HAND],
            'target_loc': self.target_loc,
            'reaction_time': rt if rt else NA,
            'movement_time': mt if mt else NA,
            'reached_item': reached_item if reached_item is not None else NA,
        }

    def trial_clean_up(self):
        clear()
        message('Press and hold spacebar', location=P.screen_c)
        flip()

        while True:
            q = pump(True)
            ui_request(queue=q)
            if key_pressed(queue=q, key=SPACE):
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
                self.stimuli[CURSOR],
                registration=5,
                location=self.get_adj_hand_pos(),
            )

        if prep:
            message(
                'Ensure spacebar is held, then tap READY',
                location=[P.screen_c[0], P.screen_c[1] // 3],  # type: ignore[unsupported-operator]
            )
            blit(
                self.stimuli[READY],
                registration=5,
                location=self.locs[READY],
            )

        blit(
            self.stimuli[NONTARGET],
            registration=5,
            location=self.locs[self.distractor_loc],
        )

        blit(
            self.stimuli[TARGET if mark_target else NONTARGET],
            registration=5,
            location=self.locs[self.target_loc],
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

        if marker_set.get('label') == self.condition[HAND]:
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
