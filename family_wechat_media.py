"""Bounded local conversion, with no account lookup, key extraction or networking.

Independently implemented from the observed V2/WXGF layout described at
https://github.com/fanyuantaier/wechatauto-replica/blob/main/wechatauto/media.py
Only the known V2 AES/clear/XOR layout and WXGF Annex-B HEVC first frame are
supported; this is not a general WeChat container or animation decoder.
AES uses macOS's public CommonCrypto API. Python packages are not required;
WXGF conversion additionally requires an explicitly selected FFmpeg executable.
"""
import ctypes
from contextlib import closing
import errno
import math
import os
from pathlib import Path
import select
import selectors
import signal
import struct
import subprocess
import sys
import tempfile
import time
import zlib

MAX_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_STDERR = 64 * 1024
_CODES = frozenset(('invalid_process', 'process_unavailable', 'process_failed', 'process_timeout',
    'process_output_limit', 'unsupported_platform', 'invalid_image_key', 'invalid_xor_key',
    'invalid_encrypted_image', 'decrypt_failed', 'invalid_png', 'unsupported_wxgf',
    'ffmpeg_unavailable', 'conversion_failed', 'media_too_large', 'media_failed',
    'media_cli_response_invalid', 'media_cli_unverified', 'media_config_changed',
    'media_config_invalid', 'media_existing_key_required', 'media_file_changed',
    'media_file_conflict', 'media_file_rejected', 'media_helper_block_unavailable',
    'media_image_invalid', 'media_job_missing', 'media_message_invalid',
    'media_message_mismatch', 'media_original_unavailable', 'media_path_rejected',
    'media_source_changed', 'media_unavailable'))


class MediaError(ValueError):
    """A fixed diagnostic code; never include command output, paths or keys."""
    def __init__(self, code):
        self.code = code if isinstance(code, str) and code in _CODES else 'media_failed'
        super().__init__(self.code)


def _kill_group(process):
    try: os.killpg(process.pid, signal.SIGKILL)
    except OSError: pass
    try: process.wait(timeout=2)
    except subprocess.TimeoutExpired: pass


def _await_exit_unreaped(process, deadline):
    """Keep the leader PID reserved until its whole group has been cleaned up."""
    remaining = deadline - time.monotonic()
    if remaining <= 0: raise MediaError('process_timeout')
    if hasattr(select, 'kqueue'):
        with closing(select.kqueue()) as queue:
            event = select.kevent(process.pid, filter=select.KQ_FILTER_PROC,
                                 flags=select.KQ_EV_ADD | select.KQ_EV_ONESHOT, fflags=select.KQ_NOTE_EXIT)
            events = queue.control([event], 1, remaining)
            if not events: raise MediaError('process_timeout')
            # Registering NOTE_EXIT after exit yields ESRCH on macOS. No poll or
            # wait has reaped this child, so its zombie still reserves the PID.
            if events[0].flags & select.KQ_EV_ERROR and events[0].data != errno.ESRCH:
                raise MediaError('process_failed')
    elif hasattr(os, 'waitid') and hasattr(os, 'WNOWAIT'):
        while os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOWAIT | os.WNOHANG) is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0: raise MediaError('process_timeout')
            time.sleep(min(0.01, remaining))
    else:
        raise MediaError('unsupported_platform')


def bounded_process(args, env, timeout, max_stdout):
    """Return stdout bytes, bounding both pipes and killing the group on failure.

The caller supplies the complete child environment. Stdin is closed, no shell
is used, and stderr is counted then discarded rather than exposed to callers.
"""
    if os.name != 'posix': raise MediaError('unsupported_platform')
    if (not isinstance(args, (list, tuple)) or not args or
        any(not isinstance(a, str) or '\0' in a for a in args) or
        not isinstance(env, dict) or any(not isinstance(k, str) or not isinstance(v, str)
                                       or '\0' in k + v or '=' in k for k, v in env.items()) or
        type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 300 or
        type(max_stdout) is not int or not 0 <= max_stdout <= MAX_BYTES):
        raise MediaError('invalid_process')
    try:
        process = subprocess.Popen(args, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=True)
    except (OSError, ValueError):
        raise MediaError('process_unavailable') from None
    output = bytearray(); error_bytes = 0; deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            for pipe in (process.stdout, process.stderr): selector.register(pipe, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0: raise MediaError('process_timeout')
                for key, _ in selector.select(remaining):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj); continue
                    if key.fileobj is process.stdout:
                        if len(output) + len(chunk) > max_stdout: raise MediaError('process_output_limit')
                        output.extend(chunk)
                    else:
                        error_bytes += len(chunk)
                        if error_bytes > MAX_STDERR: raise MediaError('process_output_limit')
        _await_exit_unreaped(process, deadline)
        # Kill same-group descendants before wait() can release/reuse the leader PID.
        _kill_group(process)
        if process.returncode != 0: raise MediaError('process_failed')
        return bytes(output)
    except subprocess.TimeoutExpired:
        raise MediaError('process_timeout') from None
    except OSError:
        raise MediaError('process_failed') from None
    finally:
        if process.returncode is None: _kill_group(process)
        process.stdout.close(); process.stderr.close()


def _aes_ecb(data, key_bytes):
    if sys.platform != 'darwin': raise MediaError('unsupported_platform')
    if not isinstance(key_bytes, (bytes, bytearray)) or len(key_bytes) not in (16, 24, 32):
        raise MediaError('invalid_image_key')
    try:
        crypt = ctypes.CDLL('/usr/lib/system/libcommonCrypto.dylib').CCCrypt
    except (OSError, AttributeError):
        raise MediaError('unsupported_platform') from None
    crypt.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
        ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p,
        ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    crypt.restype = ctypes.c_int32
    key = (ctypes.c_ubyte * len(key_bytes)).from_buffer_copy(key_bytes)
    output = ctypes.create_string_buffer(len(data)); moved = ctypes.c_size_t()
    try:
        # kCCDecrypt=1, kCCAlgorithmAES=0, kCCOptionECBMode=2. Validate padding below.
        result = crypt(1, 0, 2, key, len(key), None, data, len(data), output, len(output), ctypes.byref(moved))
        if result != 0 or moved.value != len(data): raise MediaError('decrypt_failed')
        return output.raw[:moved.value]
    finally:
        ctypes.memset(key, 0, ctypes.sizeof(key)); ctypes.memset(output, 0, ctypes.sizeof(output))


def decrypt_v2(data, key_bytes, xor_byte):
    """Decode one bounded V2 byte string using an existing in-memory key."""
    if not isinstance(data, bytes) or len(data) < 15 or data[:6] != b'\x07\x08V2\x08\x07':
        raise MediaError('invalid_encrypted_image')
    if len(data) > MAX_BYTES: raise MediaError('media_too_large')
    if type(xor_byte) is not int or not 0 <= xor_byte <= 255: raise MediaError('invalid_xor_key')
    aes_size, xor_size = struct.unpack_from('<II', data, 6)
    end = 15 + (aes_size // 16 + 1) * 16; tail = len(data) - xor_size
    if end > tail or tail < 15: raise MediaError('invalid_encrypted_image')
    head = _aes_ecb(data[15:end], key_bytes)
    padding = head[-1]
    if not 1 <= padding <= 16 or head[-padding:] != bytes([padding]) * padding:
        raise MediaError('decrypt_failed')
    if len(head) - padding != aes_size: raise MediaError('invalid_encrypted_image')
    return head[:-padding] + data[end:tail] + bytes(value ^ xor_byte for value in data[tail:])


def validate_png(data):
    """Check PNG structure, chunk CRCs and dimensions, not general pixel decoding."""
    if not isinstance(data, bytes) or len(data) < 45 or data[:8] != b'\x89PNG\r\n\x1a\n':
        raise MediaError('invalid_png')
    if len(data) > MAX_BYTES: raise MediaError('media_too_large')
    offset = 8; dimensions = None; image_data = False
    while offset < len(data):
        if len(data) - offset < 12: raise MediaError('invalid_png')
        length = struct.unpack_from('>I', data, offset)[0]; end = offset + 12 + length
        if end > len(data): raise MediaError('invalid_png')
        kind = data[offset+4:offset+8]; payload = data[offset+8:end-4]
        if zlib.crc32(data[offset+4:end-4]) & 0xffffffff != struct.unpack_from('>I', data, end-4)[0]:
            raise MediaError('invalid_png')
        if dimensions is None:
            if kind != b'IHDR' or length != 13: raise MediaError('invalid_png')
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', payload)
            depths = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
            if (not width or not height or width * height > MAX_PIXELS or depth not in depths.get(color, ())
                or compression or filtering or interlace not in (0, 1)):
                raise MediaError('invalid_png')
            dimensions = dict(width=width, height=height)
        elif kind == b'IHDR': raise MediaError('invalid_png')
        elif kind == b'IDAT': image_data = image_data or length > 0
        elif kind == b'IEND':
            if length or not image_data or end != len(data): raise MediaError('invalid_png')
            return dimensions
        offset = end
    raise MediaError('invalid_png')


def wxgf_first_frame(raw, ffmpeg_path):
    """Convert only the first HEVC frame of the supported WXGF layout to PNG."""
    if not isinstance(raw, bytes) or not raw.startswith(b'wxgf'): raise MediaError('unsupported_wxgf')
    if len(raw) > MAX_BYTES: raise MediaError('media_too_large')
    start = raw.find(b'\0\0\0\1', 4)
    if start < 4 or start + 6 > len(raw): raise MediaError('unsupported_wxgf')
    if raw[start+4] & 0x80 or not raw[start+5] & 7: raise MediaError('unsupported_wxgf')
    if not isinstance(ffmpeg_path, (str, Path)): raise MediaError('ffmpeg_unavailable')
    executable = Path(ffmpeg_path)
    if not executable.is_absolute() or not executable.is_file() or not os.access(executable, os.X_OK):
        raise MediaError('ffmpeg_unavailable')
    try:
        with tempfile.TemporaryDirectory(prefix='family-wxgf-') as directory:
            source = Path(directory) / 'frame.hevc'
            with os.fdopen(os.open(source, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), 'wb') as target:
                target.write(raw[start:])
            args = [str(executable), '-hide_banner', '-nostdin', '-v', 'error', '-xerror',
                '-protocol_whitelist', 'file,pipe', '-f', 'hevc', '-c:v', 'hevc', '-threads', '1',
                '-max_pixels', str(MAX_PIXELS), '-i', str(source), '-map', '0:v:0', '-frames:v', '1',
                '-an', '-sn', '-dn', '-c:v', 'png', '-pix_fmt', 'rgb24', '-threads', '1',
                '-f', 'image2pipe', 'pipe:1']
            # Do not pass the parent's image keys or model/account credentials to FFmpeg.
            png = bounded_process(args, {'PATH': os.defpath, 'LANG': 'C', 'LC_ALL': 'C'}, 15, MAX_BYTES)
    except OSError:
        raise MediaError('conversion_failed') from None
    return dict(data=png, **validate_png(png), first_frame_only=True)
