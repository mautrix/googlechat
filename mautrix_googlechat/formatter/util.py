import struct


# add_surrogate and del_surrogate are from
# https://github.com/LonamiWebs/Telethon/blob/master/telethon/helpers.py
def add_surrogate(text: str) -> str:
    return "".join(
        "".join(chr(y) for y in struct.unpack("<HH", x.encode("utf-16le")))
        if 0x10000 <= ord(x) <= 0x10FFFF
        else x
        for x in text
    )


def del_surrogate(text: str) -> str:
    return text.encode("utf-16", "surrogatepass").decode("utf-16")


class FormatError(Exception):
    pass
