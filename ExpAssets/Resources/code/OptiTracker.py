import os
import numpy as np
from scipy.signal import butter, sosfiltfilt
from typing import Optional


class OptiTracker(object):
    """
    A class for querying and operating on motion tracking data.

    This class processes positional data from markers, providing functionality
    to calculate velocities and positions in 3D space. It handles data loading,
    frame querying, and various spatial calculations. By default, all calculations
    use smoothed data via a dual-pass Butterworth filter to reduce noise.

    Attributes:
        marker_count (int): Number of markers to track
        sample_rate (int): Sampling rate of the tracking system in Hz
        window_size (int): Number of frames to consider for calculations
        data_dir (str): Directory path containing the tracking data files

    Methods:
        velocity(num_frames, smooth=True): Calculate velocity based on marker positions across specified number of frames
        position(smooth=True): Get current position of markers
        distance(num_frames, smooth=True): Calculate distance traveled over specified number of frames
        acceleration(num_frames, smooth=True): Calculate acceleration based on velocity changes
        accelerating(num_frames, smooth=True): Determine if the current movement is accelerating
        decelerating(num_frames, smooth=True): Determine if the current movement is decelerating

    Note:
        All methods default to using smoothed data. Set smooth=False to use raw data.
    """

    def __init__(
        self,
        marker_count: int,
        sample_rate: int = 120,
        window_size: int = 5,
        data_dir: str = "",
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

    def __validate_args(
        self, num_frames: int, min_frames: int = 1, threshold: Optional[float] = None
    ) -> int:
        """
        Validate and normalize common method arguments.

        Args:
            num_frames (int): Number of frames to validate (0 means use window_size)
            min_frames (int, optional): Minimum required frames. Defaults to 1.
            threshold (float, optional): Threshold value to validate if provided. Defaults to None.

        Returns:
            int: Normalized num_frames value (converts 0 to window_size)

        Raises:
            ValueError: If validation fails
        """
        # Normalize num_frames (0 means use window_size)
        if num_frames == 0:
            num_frames = self.__window_size

        # Validate num_frames is not negative
        if num_frames < 0:
            raise ValueError("Number of frames cannot be negative.")

        # Validate minimum frame requirement
        if num_frames < min_frames:
            if min_frames == 2:
                raise ValueError("Window size must cover at least two frames.")
            elif min_frames == 3:
                raise ValueError("Window size must cover at least three frames.")
            else:
                raise ValueError(
                    f"Window size must cover at least {min_frames} frames."
                )

        # Validate threshold if provided
        if threshold is not None and threshold < 0:
            raise ValueError("Threshold cannot be negative.")

        return num_frames

    def velocity(self, num_frames: int = 0, smooth: bool = True) -> float:
        """Calculate and return the current velocity.

        Args:
            num_frames (int, optional): Number of frames to use for calculation. Defaults to window_size.
            smooth (bool, optional): Whether to apply smoothing to the data. Defaults to True.
        """
        num_frames = self.__validate_args(num_frames, min_frames=2)
        frames = self.__query_frames(num_frames)
        return self.__velocity(frames, smooth=smooth)

    def position(self, smooth: bool = True) -> np.ndarray:
        """Get the current position of markers.

        Args:
            smooth (bool, optional): Whether to apply smoothing to the data. Defaults to True.
        """
        frame = self.__query_frames(num_frames=1)
        return self.__column_means(smooth=smooth, frames=frame)

    def distance(self, num_frames: int = 0, smooth: bool = True) -> float:
        """Calculate and return the distance traveled over the specified number of frames.

        Args:
            num_frames (int, optional): Number of frames to use for calculation. Defaults to window_size.
            smooth (bool, optional): Whether to apply smoothing to the data. Defaults to True.
        """
        num_frames = self.__validate_args(num_frames)
        frames = self.__query_frames(num_frames)
        return self.__euclidean_distance(frames, smooth=smooth)

    def acceleration(self, num_frames: int = 0, smooth: bool = True) -> float:
        """Calculate and return the current acceleration.

        Args:
            num_frames (int, optional): Number of frames to use for calculation. Defaults to window_size.
            smooth (bool, optional): Whether to apply smoothing to the data. Defaults to True.
        """
        num_frames = self.__validate_args(num_frames, min_frames=3)
        frames = self.__query_frames(num_frames)
        return self.__acceleration(frames, smooth=smooth)

    def accelerating(
        self, num_frames: int = 0, threshold: int = 10, smooth: bool = True
    ) -> bool:
        """Determine if the current movement is accelerating, defined as having an acceleration greater than the specified threshold.

        Args:
            num_frames (int, optional): Number of frames to use for calculation. Defaults to window_size.
            threshold (int, optional): Acceleration threshold in cm/s^2 to determine if accelerating. Defaults to 10.
            smooth (bool, optional): Whether to apply smoothing to the data. Defaults to True.
        """
        num_frames = self.__validate_args(num_frames, min_frames=3, threshold=threshold)
        frames = self.__query_frames(num_frames)
        return self.__acceleration(frames, smooth=smooth) > threshold

    def decelerating(self, num_frames: int = 0, smooth: bool = True) -> bool:
        """Determine if the current movement is decelerating (negative acceleration).

        Args:
            num_frames (int, optional): Number of frames to use for calculation. Defaults to window_size.
            smooth (bool, optional): Whether to apply smoothing to the data. Defaults to True.

        Returns:
            bool: True if acceleration is negative (decelerating), False otherwise.
        """
        num_frames = self.__validate_args(num_frames, min_frames=3)
        frames = self.__query_frames(num_frames)
        return self.__acceleration(frames, smooth=smooth) < 0

    def __acceleration(
        self, frames: np.ndarray = np.array([]), smooth: bool = True
    ) -> float:
        """
        Calculate acceleration using velocity data over the specified window.

        Args:
            frames (np.ndarray, optional): Array of frame data; queries last window_size frames if empty.
            smooth (bool, optional): Whether to apply smoothing to the data. Defaults to True.

        Returns:
            float: Calculated acceleration in cm/s^2
        """
        if self.__window_size < 3:
            raise ValueError("Window size must cover at least three frames.")

        if len(frames) == 0:
            frames = self.__query_frames()

        velocity_start = self.__velocity(
            frames[: self.__window_size // 2], smooth=smooth
        )
        velocity_end = self.__velocity(frames[self.__window_size // 2 :], smooth=smooth)

        return (velocity_end - velocity_start) / (
            (self.__window_size / 2) / self.__sample_rate
        )

    def __velocity(
        self, frames: np.ndarray = np.array([]), smooth: bool = True
    ) -> float:
        """
        Calculate velocity using position data over the specified window.

        Args:
            frames (np.ndarray, optional): Array of frame data; queries last window_size frames if empty.
            smooth (bool, optional): Whether to apply smoothing to the data. Defaults to True.

        Returns:
            float: Calculated velocity in cm/s
        """
        if self.__window_size < 2:
            raise ValueError("Window size must cover at least two frames.")

        if len(frames) == 0:
            frames = self.__query_frames()

        euclidean_distance = self.__euclidean_distance(frames, smooth=smooth)

        return euclidean_distance / (self.__window_size / self.__sample_rate)

    def __euclidean_distance(
        self, frames: np.ndarray = np.array([]), smooth: bool = True
    ) -> float:
        """
        Calculate Euclidean distance between first and last frames.

        Args:
            frames (np.ndarray, optional): Array of frame data; queries last window_size frames if empty.
            smooth (bool, optional): Whether to apply smoothing to the data. Defaults to True.

        Returns:
            float: Euclidean distance
        """

        if frames.size == 0:
            frames = self.__query_frames()

        positions = self.__column_means(smooth=smooth, frames=frames)

        return float(
            np.sqrt(
                (positions["pos_x"][-1] - positions["pos_x"][0]) ** 2
                + (positions["pos_y"][-1] - positions["pos_y"][0]) ** 2
                + (positions["pos_z"][-1] - positions["pos_z"][0]) ** 2
            )
        )

    def __smooth(
        self,
        order=4,
        cutoff=6,
        filtype="low",
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
                ("frame_number", "i8"),
                ("pos_x", "i8"),
                ("pos_y", "i8"),
                ("pos_z", "i8"),
            ],
        )

        butt = butter(
            N=order,
            Wn=cutoff,
            btype=filtype,
            output="sos",
            fs=self.__sample_rate,
        )

        smooth["pos_x"] = sosfiltfilt(sos=butt, x=frames["pos_x"])
        smooth["pos_y"] = sosfiltfilt(sos=butt, x=frames["pos_y"])
        smooth["pos_z"] = sosfiltfilt(sos=butt, x=frames["pos_z"])

        return smooth

    def __column_means(
        self, smooth: bool = True, frames: np.ndarray = np.array([])
    ) -> np.ndarray:
        """
        Calculate column means of position data.

        Args:
            smooth (bool, optional): Whether to apply smoothing before calculating means. Defaults to True.
            frames (np.ndarray, optional): Array of frame data; queries last window_size frames if empty.

        Returns:
            np.ndarray: Array of mean positions
        """
        if len(frames) == 0:
            frames = self.__query_frames()

        # Create output array with the correct dtype
        means = np.zeros(
            len(frames) // self.__marker_count,
            dtype=[
                ("frame_number", "i8"),
                ("pos_x", "i8"),
                ("pos_y", "i8"),
                ("pos_z", "i8"),
            ],
        )

        # Group by marker (every nth row where n is marker_count)
        start = min(frames["frame_number"])
        stop = max(frames["frame_number"]) + 1

        for frame_number in range(start, stop):
            this_frame = frames[frames["frame_number"] == frame_number,]

            idx = frame_number - start
            means[idx]["frame_number"] = frame_number
            means[idx]["pos_x"] = np.mean(this_frame["pos_x"])
            means[idx]["pos_y"] = np.mean(this_frame["pos_y"])
            means[idx]["pos_z"] = np.mean(this_frame["pos_z"])

        # Apply smoothing if requested
        if smooth:
            means = self.__smooth(frames=means)

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

        if self.__data_dir == "":
            raise ValueError("No data directory was set.")

        if not os.path.exists(self.__data_dir):
            raise FileNotFoundError(f"Data directory not found at:\n{self.__data_dir}")

        if num_frames < 0:
            raise ValueError("Number of frames cannot be negative.")

        with open(self.__data_dir, "r") as file:
            header = file.readline().strip().split(",")

        if any(
            col not in header for col in ["frame_number", "pos_x", "pos_y", "pos_z"]
        ):
            raise ValueError(
                "Data file must contain columns named frame_number, pos_x, pos_y, pos_z."
            )

        dtype_map = [
            # coerce expected columns to float, int, string (default)
            (
                name,
                (
                    "float"
                    if name in ["pos_x", "pos_y", "pos_z"]
                    else "int"
                    if name == "frame_number"
                    else "U32"
                ),
            )
            for name in header
        ]

        # read in data now that columns have been validated and typed
        data = np.genfromtxt(
            self.__data_dir, delimiter=",", dtype=dtype_map, skip_header=1
        )

        for col in ["pos_x", "pos_y", "pos_z"]:
            # rescale from mm to cm
            data[col] = np.rint(data[col] * 100).astype(np.int32)

        if num_frames == 0:
            num_frames = self.__window_size

        # Calculate which frames to include
        last_frame = data["frame_number"][-1]
        lookback = last_frame - num_frames

        # Filter for relevant frames
        data = data[data["frame_number"] > lookback]

        return data
