import os
import numpy as np
import sqlite3
from scipy.signal import butter, sosfiltfilt


# from klibs.KLDatabase import KLDatabase as kld

# TODO:
# grab first frame, row count indicates num markers tracked.
# incorporate checks to ensure frames queried match expected marker count
# refactor nomeclature about frame indexing/querying


class OptiTracker(object):
    """
    A class for querying and operating on motion tracking data.

    This class processes positional data from markers, providing functionality
    to calculate velocities and positions in 3D space. It handles data loading,
    frame querying, and various spatial calculations.

    Attributes:
        marker_count (int): Number of markers to track
        sample_rate (int): Sampling rate of the tracking system in Hz
        window_size (int): Number of frames to consider for calculations
        data_dir (str): Directory path containing the tracking data files

    Methods:
        velocity(num_frames): Calculate velocity based on marker positions across specified number of frames
        position(): Get current position of markers
        distance(num_frames: int): Calculate distance traveled over specified number of frames
    """

    def __init__(
        self,
        marker_count: int,
        sample_rate: int = 120,
        window_size: int = 5,
        data_dir: str = '',
        db_name: str = 'optitracker.db',
    ):
        """
        Initialize the OptiTracker object.

        Args:
            marker_count (int): Number of markers to track
            sample_rate (int, optional): Sampling rate in Hz. Defaults to 120.
            window_size (int, optional): Number of frames for calculations. Defaults to 5.
            data_dir (str, optional): Path to data directory. Defaults to empty string.
        """

        if marker_count:
            self.__marker_count = marker_count

        self.__sample_rate = sample_rate
        self.__data_dir = data_dir
        self.__window_size = window_size
        # self.db = self.__connect(db_name)

        # self.cursor = self.db.cursor()

        db_scheme = """
        CREATE TABLE IF NOT EXISTS frames (
            frame_number INTEGER PRIMARY KEY,
            pos_x REAL,
            pos_y REAL,
            pos_z REAL
        )
        """

        # self.cursor.execute(db_scheme)

    # @property
    # def database(self) -> str:
    #     """Get the name of the database file."""
    #     return self.__database
    #
    # @database.setter
    # def database(self, database: str) -> None:
    #     """Set the name of the database file."""
    #     self.__database = database

    @property
    def marker_count(self) -> int:
        """Get the number of markers to track."""
        return self.__marker_count

    @marker_count.setter
    def marker_count(self, marker_count: int) -> None:
        """Set the number of markers to track."""
        self.__marker_count = marker_count

    @property
    def data_dir(self) -> str:
        """Get the data directory path."""
        return self.__data_dir

    @data_dir.setter
    def data_dir(self, data_dir: str) -> None:
        """Set the data directory path."""
        self.__data_dir = data_dir

    @property
    def sample_rate(self) -> int:
        """Get the sampling rate."""
        return self.__sample_rate

    @sample_rate.setter
    def sample_rate(self, sample_rate: int) -> None:
        """Set the sampling rate."""
        self.__sample_rate = sample_rate

    @property
    def window_size(self) -> int:
        """Get the window size."""
        return self.__window_size

    @window_size.setter
    def window_size(self, window_size: int) -> None:
        """Set the window size."""
        self.__window_size = window_size

    def velocity(self, num_frames: int = 0) -> float:
        """Calculate and return the current velocity."""
        if num_frames == 0:
            num_frames = self.__window_size

        if num_frames < 2:
            raise ValueError('Window size must cover at least two frames.')

        frames = self.__query_frames(num_frames)
        return self.__velocity(frames)

    def position(self) -> np.ndarray:
        """Get the current position of markers."""
        frame = self.__query_frames(num_frames=1)
        return self.__column_means(smooth=False, frames=frame)

    def distance(self, num_frames: int = 0) -> float:
        """Calculate and return the distance traveled over the specified number of frames."""

        if num_frames == 0:
            num_frames = self.__window_size

        frames = self.__query_frames(num_frames)
        return self.__euclidean_distance(frames)

    def __velocity(self, frames: np.ndarray = np.array([])) -> float:
        """
        Calculate velocity using position data over the specified window.

        Args:
            frames (np.ndarray, optional): Array of frame data; queries last window_size frames if empty.

        Returns:
            float: Calculated velocity in cm/s
        """
        if self.__window_size < 2:
            raise ValueError('Window size must cover at least two frames.')

        if len(frames) == 0:
            frames = self.__query_frames()

        euclidean_distance = self.__euclidean_distance(frames)

        return euclidean_distance / (self.__window_size / self.__sample_rate)

    def __euclidean_distance(self, frames: np.ndarray = np.array([])) -> float:
        """
        Calculate Euclidean distance between first and last frames.

        Args:
            frames (np.ndarray, optional): Array of frame data; queries last window_size frames if empty.

        Returns:
            float: Euclidean distance
        """

        if frames.size == 0:
            frames = self.__query_frames()

        positions = self.__column_means(smooth=True, frames=frames)

        # print("[__euclidean_distance()]")
        # print("Frames queried:")
        # pprint(frames)
        # print("Calculated postion:")
        # pprint(positions)

        return float(
            np.sqrt(
                (positions['pos_x'][-1] - positions['pos_x'][0]) ** 2
                + (positions['pos_y'][-1] - positions['pos_y'][0]) ** 2
                + (positions['pos_z'][-1] - positions['pos_z'][0]) ** 2
            )
        )

    # TODO: reduce dependencies by hand-rolling a butterworth filter
    # TODO: but first make sure this isn't a bad idea.

    def __smooth(
        self,
        order=2,
        cutoff=10,
        filtype='low',
        frames: np.ndarray = np.array([]),
    ) -> np.ndarray:
        """
        Apply a dual-pass Butterworth filter to positional data.

        Args:
            order (int, optional): Order of the Butterworth filter. Defaults to 2.
            cutoff (int, optional): Cutoff frequency in Hz. Defaults to 10.
            filtype (str, optional): Type of filter to apply. Defaults to "low".
            frames (np.ndarray, optional): Array of frame data; queries last window_size frames if empty.

        Returns:
            np.ndarray: Array of filtered positions
        """
        if len(frames) == 0:
            frames = self.__query_frames()

        # Create output array with the correct dtype
        smooth = np.zeros(
            len(frames),
            dtype=[
                ('frame_number', 'i8'),
                ('pos_x', 'i8'),
                ('pos_y', 'i8'),
                ('pos_z', 'i8'),
            ],
        )

        butt = butter(
            N=order,
            Wn=cutoff,
            btype=filtype,
            output='sos',
            fs=self.__sample_rate,
        )

        # print("[__smooth()]")
        # print("frames:")
        # pprint(frames)

        smooth['pos_x'] = sosfiltfilt(sos=butt, x=frames['pos_x'])
        smooth['pos_y'] = sosfiltfilt(sos=butt, x=frames['pos_y'])
        smooth['pos_z'] = sosfiltfilt(sos=butt, x=frames['pos_z'])

        return smooth

    def __column_means(
        self, smooth: bool = True, frames: np.ndarray = np.array([])
    ) -> np.ndarray:
        """
        Calculate column means of position data.

        Args:
            frames (np.ndarray, optional): Array of frame data; queries last window_size frames if empty.

        Returns:
            np.ndarray: Array of mean positions

        Note:
            Currently applies smoothing function to generate means.
            This may (and should) be done on raw data within __query_frames instead.
        """
        if len(frames) == 0:
            frames = self.__query_frames()

        # print("OptiTracker column_means, got frames:")
        # pprint(frames)

        # Create output array with the correct dtype
        means = np.zeros(
            len(frames) // self.__marker_count,
            dtype=[
                ('frame_number', 'i8'),
                ('pos_x', 'i8'),
                ('pos_y', 'i8'),
                ('pos_z', 'i8'),
            ],
        )

        # Group by marker (every nth row where n is marker_count)
        start = min(frames['frame_number'])
        stop = max(frames['frame_number']) + 1

        for frame_number in range(start, stop):
            this_frame = frames[
                frames['frame_number'] == frame_number,
            ]

            # print("OptiTracker column_means, this frame:")
            # pprint(this_frame)

            # if not len(frame):
            #     tmp = frame_number - 1
            #     while not len(frame) and tmp >= start:
            #         frame = frames[frames["frame_number"] == tmp,]
            #         tmp -= 1

            idx = frame_number - start
            means[idx]['pos_x'] = np.mean(this_frame['pos_x'])
            means[idx]['pos_y'] = np.mean(this_frame['pos_y'])
            means[idx]['pos_z'] = np.mean(this_frame['pos_z'])

            idx += 1

            # except RuntimeWarning as e:
            #     means[idx]["pos_x"] = 0.0
            #     means[idx]["pos_y"] = 0.0
            #     means[idx]["pos_z"] = 0.0

        # if smooth:
        #     means = self.__smooth(frames=means)

        return means

    def __query_frames(self, num_frames: int = 0) -> np.ndarray:
        """
        Query and process frame data from the data file.

        Args:
            num_frames (int, optional): Number of frames to query. Defaults to window_size when empty.

        Returns:
            np.ndarray: Array of queried frame data

        Raises:
            ValueError: If data directory is not set or data format is invalid
            FileNotFoundError: If data directory does not exist
        """

        if self.__data_dir == '':
            raise ValueError('No data directory was set.')

        if not os.path.exists(self.__data_dir):
            raise FileNotFoundError(
                f'Data directory not found at:\n{self.__data_dir}'
            )

        if num_frames < 0:
            raise ValueError('Number of frames cannot be negative.')

        with open(self.__data_dir, 'r') as file:
            header = file.readline().strip().split(',')

        if any(
            col not in header
            for col in ['frame_number', 'pos_x', 'pos_y', 'pos_z']
        ):
            raise ValueError(
                'Data file must contain columns named frame_number, pos_x, pos_y, pos_z.'
            )

        dtype_map = [
            # coerce expected columns to float, int, string (default)
            (
                name,
                (
                    'float'
                    if name in ['pos_x', 'pos_y', 'pos_z']
                    else 'int'
                    if name == 'frame_number'
                    else 'U32'
                ),
            )
            for name in header
        ]

        # read in data now that columns have been validated and typed
        data = np.genfromtxt(
            self.__data_dir, delimiter=',', dtype=dtype_map, skip_header=1
        )

        for col in ['pos_x', 'pos_y', 'pos_z']:
            # rescale from mm to cm
            data[col] = np.rint(data[col] * 100).astype(np.int32)

        if num_frames == 0:
            num_frames = self.__window_size

        # Calculate which frames to include
        last_frame = data['frame_number'][-1]
        lookback = last_frame - num_frames

        # Filter for relevant frames
        data = data[data['frame_number'] > lookback]

        return data

    def __connect(self, db_name: str = 'optitracker.db') -> sqlite3.Connection:
        """
        Connect to the SQLite database.

        Returns:
            sqlite3.Connection: Connection object
        """
        return sqlite3.connect(db_name)
