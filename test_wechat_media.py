"""Public AES vectors and synthetic media/processes only; no WeChat or account data."""
import base64
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zlib

import family_wechat_media as media

# FIPS-197 AES-128 example; the second block encrypts a full PKCS7 padding block.
PUBLIC_KEY = bytes(range(16))
PLAINTEXT = bytes.fromhex('00112233445566778899aabbccddeeff')
CIPHERTEXT = bytes.fromhex('69c4e0d86a7b0430d8cdb78070b4c55a954f64f2e4e86e9eee82d20216684899')
# One green 32x24 frame generated locally by FFmpeg/libx265, with encoder SEI omitted.
HEVC = base64.b64decode('AAAAAUABDAH//wFgAAADAJAAAAMAAAMAHpWYCQAAAAFCAQEBYAAAAwCQAAADAAADAB6gQhlllZqvK8BaAgAAAwACAAADADIQAAAAAUQBwXPQiQAAASgBrx2A8A4I/4l59xB7l2nF2lPA')
WXGF = b'wxgf' + b'\0' * 8 + HEVC
FFMPEG = shutil.which('ffmpeg')


def chunk(kind, payload):
    return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff)


def png(width=1, height=1):
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\0\x00\x80\x00')) + chunk(b'IEND', b''))


class MediaTests(unittest.TestCase):
    def code(self, expected, function, *args):
        with self.assertRaises(media.MediaError) as error: function(*args)
        self.assertEqual(error.exception.code, expected)
        self.assertEqual(str(error.exception), expected)

    @unittest.skipUnless(sys.platform == 'darwin', 'CommonCrypto requires macOS')
    def test_public_aes_and_v2_boundaries(self):
        self.assertEqual(media._aes_ecb(CIPHERTEXT[:16], PUBLIC_KEY), PLAINTEXT)
        for tail in (b'', b'synthetic tail'):
            middle = b'synthetic clear bytes'; xor = 0x5a
            data = b'\x07\x08V2\x08\x07' + struct.pack('<II', 16, len(tail)) + b'\0' + CIPHERTEXT + middle + bytes(b ^ xor for b in tail)
            self.assertEqual(media.decrypt_v2(data, bytearray(PUBLIC_KEY), xor), PLAINTEXT + middle + tail)
        prefix = b'\x07\x08V2\x08\x07'
        self.code('invalid_encrypted_image', media.decrypt_v2, prefix + struct.pack('<II', 17, 0) + b'\0' + CIPHERTEXT, PUBLIC_KEY, 0)
        self.code('decrypt_failed', media.decrypt_v2, prefix + struct.pack('<II', 15, 0) + b'\0' + CIPHERTEXT[:16], PUBLIC_KEY, 0)
        valid = prefix + struct.pack('<II', 16, 0) + b'\0' + CIPHERTEXT
        self.code('invalid_image_key', media.decrypt_v2, valid, b'bad', 0)
        self.code('invalid_xor_key', media.decrypt_v2, valid, PUBLIC_KEY, 256)
        self.code('invalid_xor_key', media.decrypt_v2, valid, PUBLIC_KEY, True)

    def test_invalid_encrypted_lengths(self):
        for data in (b'', b'not a V2 image', b'\x07\x08V2\x08\x07' + struct.pack('<II', 0xffffffff, 1) + b'\0',
                     b'\x07\x08V2\x08\x07' + struct.pack('<II', 16, 100) + b'\0' + CIPHERTEXT):
            self.code('invalid_encrypted_image', media.decrypt_v2, data, PUBLIC_KEY, 0)

    def test_png_structure_crc_and_pixels(self):
        self.assertEqual(media.validate_png(png()), dict(width=1, height=1))
        for data in (png()[:-1], png()+b'extra', png()[:29]+b'bad!'+png()[33:], png(width=0),
                     png(width=media.MAX_PIXELS+1), png()[:-12], png()[:33]+chunk(b'IEND', b'')):
            self.code('invalid_png', media.validate_png, data)
        self.code('unsupported_wxgf', media.wxgf_first_frame, b'wxgf-no-stream', '/usr/bin/false')
        self.code('ffmpeg_unavailable', media.wxgf_first_frame, WXGF, 'ffmpeg')

    @unittest.skipUnless(os.name == 'posix', 'Process groups require POSIX')
    def test_bounded_process_does_not_return_diagnostics(self):
        args = [sys.executable, '-c', 'import sys;sys.stdout.buffer.write(b"ok")']
        self.assertEqual(media.bounded_process(args, {}, 2, 2), b'ok')
        self.code('process_output_limit', media.bounded_process, args, {}, 2, 1)
        self.code('process_output_limit', media.bounded_process,
                  [sys.executable, '-c', 'import sys;sys.stderr.write("x"*100000)'], {}, 2, 1)
        self.code('process_failed', media.bounded_process,
                  [sys.executable, '-c', 'import sys;sys.stderr.write("synthetic-private-value");sys.exit(1)'], {}, 2, 100)

    @unittest.skipUnless(os.name == 'posix', 'Process groups require POSIX')
    def test_fast_exit_and_closed_pipes(self):
        for _ in range(100):
            self.assertEqual(media.bounded_process(['/usr/bin/true'], {}, 2, 0), b'')
        self.code('process_failed', media.bounded_process, ['/usr/bin/false'], {}, 2, 0)
        self.code('process_timeout', media.bounded_process,
                  [sys.executable, '-c', 'import os,time;os.close(1);os.close(2);time.sleep(5)'], {}, 0.2, 0)

    @unittest.skipUnless(os.name == 'posix', 'Process groups require POSIX')
    def test_timeout_cleans_up_descendant(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-media-process-') as directory:
            output = Path(directory) / 'must-not-be-written'
            code = 'import os,sys,time;pid=os.fork();time.sleep(0.7 if pid==0 else 5);open(sys.argv[1],"w").write("synthetic")'
            self.code('process_timeout', media.bounded_process, [sys.executable, '-c', code, str(output)], {}, 0.2, 100)
            time.sleep(0.8)
            self.assertFalse(output.exists(), 'Timed-out child and descendant are both stopped')

    @unittest.skipUnless(os.name == 'posix', 'Process groups require POSIX')
    def test_exited_parent_cleans_up_descendant_with_or_without_inherited_pipes(self):
        for close_pipes in (False, True):
            with self.subTest(close_pipes=close_pipes), tempfile.TemporaryDirectory(prefix='synthetic-media-exit-') as directory:
                output = Path(directory) / 'must-not-be-written'
                code = ('import os,sys,time\npid=os.fork()\nif pid:\n os.write(1,b"ok");os._exit(0)\n'
                        + ('os.close(1);os.close(2)\n' if close_pipes else '')
                        + 'time.sleep(0.7)\nopen(sys.argv[1],"w").write("synthetic")\n')
                args = [sys.executable, '-c', code, str(output)]
                if close_pipes: self.assertEqual(media.bounded_process(args, {}, 0.3, 100), b'ok')
                else: self.code('process_timeout', media.bounded_process, args, {}, 0.2, 100)
                time.sleep(0.8)
                self.assertFalse(output.exists(), 'A descendant cannot outlive the completed command')

    def test_error_codes_remain_explicit(self):
        for code in ('media_existing_key_required', 'media_path_rejected', 'media_message_mismatch', 'media_unavailable'):
            self.assertEqual(str(media.MediaError(code)), code)
        self.assertEqual(str(media.MediaError('synthetic-secret-not-a-code')), 'media_failed')

    def test_conversion_arguments_and_environment(self):
        with patch.object(media, 'bounded_process', return_value=png()) as run:
            with patch.dict(os.environ, {'WECHAT_CLI_IMAGE_KEY': 'synthetic-private-key'}):
                result = media.wxgf_first_frame(WXGF, sys.executable)
        self.assertEqual(result, dict(data=png(), width=1, height=1, first_frame_only=True))
        args, env, timeout, bound = run.call_args.args
        self.assertEqual(env, {'PATH': os.defpath, 'LANG': 'C', 'LC_ALL': 'C'})
        self.assertNotIn('synthetic-private-key', repr(args))
        self.assertEqual(args[args.index('-protocol_whitelist')+1], 'file,pipe')
        self.assertEqual(args[args.index('-f')+1], 'hevc')
        self.assertEqual(args[args.index('-max_pixels')+1], str(media.MAX_PIXELS))
        self.assertEqual((timeout, bound), (15, media.MAX_BYTES))
        self.assertFalse(Path(args[args.index('-i')+1]).exists(), 'Temporary plaintext was removed')

    @unittest.skipUnless(FFMPEG, 'Install FFmpeg to check synthetic HEVC conversion')
    def test_synthetic_hevc_first_frame(self):
        result = media.wxgf_first_frame(WXGF, FFMPEG)
        self.assertEqual((result['width'], result['height']), (32, 24))
        self.assertIs(result['first_frame_only'], True)
        self.assertEqual(media.validate_png(result['data']), dict(width=32, height=24))


if __name__ == '__main__': unittest.main()
