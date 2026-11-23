"""Extrae el recorte de trabajo usando Media Foundation en Windows."""

import argparse
import ctypes as c
from pathlib import Path
from uuid import UUID

from seguimiento import ROI
from PIL import Image

P = c.c_void_p
U = c.c_uint32
Q = c.c_uint64
L = c.c_int64
H = c.c_long
W = c.c_wchar_p

def guid(s):
    return (c.c_ubyte * 16).from_buffer_copy(UUID(s).bytes_le)

def check(hr, note):
    if hr < 0:
        raise OSError(f"{note}: {hr & 0xffffffff:08x}")

def call(obj, index, sig, *args, result=H):
    table = c.cast(obj, c.POINTER(c.POINTER(P))).contents
    return c.WINFUNCTYPE(result, P, *sig)(table[index])(obj, *args)

def invoke(dll, name, sig, *args):
    f = getattr(dll, name)
    f.argtypes = sig
    f.restype = H
    check(f(*args), name)

def pair(obj, key):
    value = Q()
    check(call(obj, 8, [P, P], guid(key), c.byref(value)), key)
    return value.value >> 32, value.value & 0xffffffff



def decode(video, destination):
    mf = c.WinDLL("mfplat")
    rw = c.WinDLL("mfreadwrite")
    ole = c.WinDLL("ole32")
    invoke(ole, "CoInitializeEx", [P, U], None, 0)
    invoke(mf, "MFStartup", [U, U], 0x20070, 0)
    attributes, reader, mt, active, native = (P() for _ in range(5))
    invoke(mf, "MFCreateAttributes", [P, U], c.byref(attributes), 1)
    check(call(attributes, 21, [P, U], guid("fb394f3d-ccf1-42ee-bbb3-f9b845d5681d"), 1), "enable video processing")
    path = video.resolve()
    invoke(rw, "MFCreateSourceReaderFromURL", [W, P, P], str(path), attributes, c.byref(reader))
    stream = 0xfffffffc
    check(call(reader, 5, [U, U, P], stream, 0, c.byref(native)), "native type")
    fps = pair(native, "c459a2e8-3d2c-4e44-b132-fee5156c7bb0")
    invoke(mf, "MFCreateMediaType", [P], c.byref(mt))
    for key, value in (
        ("48eba18e-f8c9-4687-bf11-0a74c9f96a8f", "73646976-0000-0010-8000-00aa00389b71"),
        ("f7e34c9a-42e8-4714-b74b-cb29d72c35e5", "00000016-0000-0010-8000-00aa00389b71"),
    ):
        check(call(mt, 24, [P, P], guid(key), guid(value)), "set media type attribute")
    check(call(reader, 7, [U, P, P], stream, None, mt), "set RGB32")
    check(call(reader, 6, [U, P], stream, c.byref(active)), "active type")
    width, height = pair(active, "1652c33d-d6b2-4012-b834-72030849a37d")
    print(f"{width}x{height} fps={fps[0]}/{fps[1]}", flush=True)
    destination.mkdir(parents=True, exist_ok=False)
    count = 0
    while True:
        flags, sample, ts = U(), P(), L()
        check(call(reader, 9, [U, U, P, P, P, P], stream, 0, None, c.byref(flags), c.byref(ts), c.byref(sample)), "read sample")
        if flags.value & 2:
            break
        if not sample:
            continue
        buffer, data, length = P(), P(), U()
        check(call(sample, 41, [P], c.byref(buffer)), "sample buffer")
        surface, pitch = P(), c.c_int32()
        hr = call(buffer, 0, [P, P], guid("7dc9d5f9-9ed9-44ec-9bbf-0600bb589fbb"), c.byref(surface))
        if hr >= 0:
            check(call(surface, 3, [P, P], c.byref(data), c.byref(pitch)), "Lock2D")
            if count == 0:
                print(f"pitch={pitch.value}", flush=True)
            raw = b"".join(c.string_at(data.value + y * pitch.value, width * 4) for y in range(height))
            check(call(surface, 4, []), "Unlock2D")
            call(surface, 2, [], result=U)
            picture = Image.frombytes("RGB", (width, height), raw, "raw", "BGRX")
        else:
            check(call(buffer, 3, [P, P, P], c.byref(data), None, c.byref(length)), "lock buffer")
            stride = U()
            hr_stride = call(active, 7, [P, P], guid("644b4e48-1e02-4516-b0eb-c01ca9d49ac6"), c.byref(stride))
            if count == 0:
                print(f"buffer length={length.value}, stride attr={c.c_int32(stride.value).value}, result={hr_stride}", flush=True)
            raw = c.string_at(data, length.value)
            check(call(buffer, 4, []), "unlock buffer")
            pitch_value = abs(c.c_int32(stride.value).value) if hr_stride >= 0 else width * 4
            picture = Image.frombytes("RGB", (width, height), raw, "raw", "BGRX", pitch_value, -1)
        picture.crop(ROI).save(destination / f"{count:05}-{ts.value / 10_000_000:.7f}.png")
        call(buffer, 2, [], result=U)
        call(sample, 2, [], result=U)
        count += 1
    for interface in (active, mt, native, reader, attributes):
        call(interface, 2, [], result=U)
    invoke(mf, "MFShutdown", [])
    ole.CoUninitialize()
    print(f"Cuadros extraidos: {count}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("destino", type=Path)
    args = parser.parse_args()
    if not args.video.is_file():
        parser.error(f"No se encuentra el video: {args.video}")
    if args.destino.exists():
        parser.error(f"El destino debe ser una carpeta nueva: {args.destino}")
    decode(args.video, args.destino)
