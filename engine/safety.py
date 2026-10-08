"""Read-only sources; writes restricted to private app storage or local temp storage."""
import tempfile
import ctypes
from pathlib import Path

def validate_image_output(source, output):
    """Saved images may export directly to a user-selected fixed disk, never camera media."""
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_file() or output == source or source.is_relative_to(output):
        raise ValueError('Choose a saved regular-file image and a separate output folder.')
    parent = output if output.exists() else output.parent
    if not parent.is_dir():
        raise ValueError('Choose an existing destination folder.')
    # Use native volume properties in both editions; no diskutil subprocess or raw access.
    cf = ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
    cf.CFURLCreateFromFileSystemRepresentation.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_bool]
    cf.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
    cf.CFURLCopyResourcePropertyForKey.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
    cf.CFURLCopyResourcePropertyForKey.restype = ctypes.c_bool
    cf.CFBooleanGetValue.argtypes = [ctypes.c_void_p]
    cf.CFBooleanGetValue.restype = ctypes.c_bool
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    path = str(parent).encode()
    url = cf.CFURLCreateFromFileSystemRepresentation(None, path, len(path), True)
    if not url:
        raise ValueError('Could not inspect the output volume.')
    try:
        for name in ('kCFURLVolumeIsReadOnlyKey', 'kCFURLVolumeIsRemovableKey'):
            key = ctypes.c_void_p.in_dll(cf, name)
            value = ctypes.c_void_p()
            if not cf.CFURLCopyResourcePropertyForKey(url, key, ctypes.byref(value), None) or not value:
                raise ValueError('Could not inspect the output volume.')
            try:
                if cf.CFBooleanGetValue(value):
                    raise ValueError('Save photos to a writable fixed disk, not removable camera media.')
            finally:
                cf.CFRelease(value)
    finally:
        cf.CFRelease(url)
    return output

def validate_output(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output == source or source.is_relative_to(output) or (source.is_dir() and output.is_relative_to(source)):
        raise ValueError('Results must stay outside the source tree.')
    roots = [(Path.home() / 'Library/Application Support/CardRescue').resolve(), Path(tempfile.gettempdir()).resolve()]
    if not any(output.is_relative_to(root) and output != root for root in roots):
        raise ValueError('Results must stay in private app storage, away from camera media.')
    return output
