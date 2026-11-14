"""Enumerate Windows capture devices in the order used by OpenCV CAP_DSHOW."""

import ctypes as c
from contextlib import ExitStack
from uuid import UUID


HRESULT = c.c_long
PTR = c.c_void_p
GUID = c.c_ubyte * 16


def guid(value):
    return GUID.from_buffer_copy(UUID(value).bytes_le)


def method(obj, slot, result, *args):
    # COM interfaces expose methods through a vtable. The first argument is self.
    table = c.cast(obj, c.POINTER(c.POINTER(PTR))).contents
    return c.WINFUNCTYPE(result, PTR, *args)(table[slot])


def release(obj):
    method(obj, 2, c.c_ulong)(obj)  # IUnknown::Release


class Variant(c.Structure):
    _fields_ = [("type", c.c_ushort), ("reserved", c.c_ushort * 3), ("pointers", PTR * 2)]


def label(bag):
    read = method(bag, 3, HRESULT, c.c_wchar_p, c.POINTER(Variant), PTR)
    for name in ("FriendlyName", "Description"):
        value = Variant()
        try:
            if read(bag, name, c.byref(value), None) >= 0 and value.type == 8 and value.pointers[0]:
                return c.wstring_at(value.pointers[0])
        finally:
            c.windll.oleaut32.VariantClear(c.byref(value))
    return None


def cameras():
    ole = c.windll.ole32
    initialized = ole.CoInitializeEx(None, 0)
    # A caller already initialized in another apartment can still enumerate.
    if initialized < 0 and initialized != -2147417850:  # RPC_E_CHANGED_MODE
        return []
    with ExitStack() as stack:
        if initialized >= 0:
            stack.callback(ole.CoUninitialize)
        system = PTR()
        if ole.CoCreateInstance(
            c.byref(guid("62BE5D10-60EB-11D0-BD3B-00A0C911CE86")), None, 1,
            c.byref(guid("29840822-5B84-11D0-BD3B-00A0C911CE86")), c.byref(system),
        ) < 0:
            return []
        stack.callback(release, system)

        category = guid("860BB310-5D01-11D0-BD3B-00A0C911CE86")
        enumerator = PTR()
        create = method(system, 3, HRESULT, c.POINTER(GUID), c.POINTER(PTR), c.c_ulong)
        if create(system, c.byref(category), c.byref(enumerator), 0) != 0:
            return []
        stack.callback(release, enumerator)
        next_moniker = method(enumerator, 3, HRESULT, c.c_ulong, c.POINTER(PTR), PTR)
        bag_id = guid("55272A00-42CB-11CE-8135-00AA004BB851")
        found = []
        for index in range(16):  # CameraInput accepts indices 0–15.
            moniker = PTR()
            if next_moniker(enumerator, 1, c.byref(moniker), None) != 0:
                break
            with ExitStack() as item:
                item.callback(release, moniker)
                bag = PTR()
                bind = method(moniker, 9, HRESULT, PTR, PTR, c.POINTER(GUID), c.POINTER(PTR))
                name = None
                if bind(moniker, None, None, c.byref(bag_id), c.byref(bag)) >= 0:
                    item.callback(release, bag)
                    name = label(bag)
                found.append({"index": index, "label": name or f"Camera {index}"})
        return found
