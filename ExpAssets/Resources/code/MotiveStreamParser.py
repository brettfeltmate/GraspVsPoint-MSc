# type: ignore
from typing import Union, Container
from dataStructures import unlabeledMarkerStruct, labeledMarkerStruct, rigidBodyStruct
from construct import Int32ul, CString


class MotiveStreamParser(object):
    def __init__(self, stream: bytes):
        self.__stream = memoryview(stream)
        self.__offset = 0

        self.__structures = {
            "label": CString("utf8"),
            "size": Int32ul,
            "count": Int32ul,
            "frame_number": Int32ul,
            "unlabeled_marker": unlabeledMarkerStruct,
            "legacy_marker": unlabeledMarkerStruct,
            "labeled_marker": labeledMarkerStruct,
            "rigid_body": rigidBodyStruct,
        }

    def seek(self, by: int) -> None:
        self.__offset += by

    def tell(self) -> int:
        return self.__offset

    def sizeof(self, asset_type: str, asset_count: int = 1) -> int:
        return self.__structures[asset_type].sizeof() * asset_count

    def parse(self, asset_type: str) -> Union[str, int, Container]:
        struct = self.__structures[asset_type]
        contents = struct.parse(self.__stream[self.__offset :])

        if asset_type == "label":
            self.seek(len(contents) + 1)
        else:
            self.seek(struct.sizeof())

        return contents
