# cerbero - a multi-platform build system
# Copyright (C) 2026 GStreamer maintainers
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.

import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

from cerbero.errors import ChecksumError
from cerbero.utils import verify_checksum
from cerbero.utils import shell

EXPECTED_CONTENTS = b'expected contents'
EXPECTED_CHECKSUM = '532e548a772806301a0a36d9e3d04b7b38e8d55e80edbeb750cc187907d76287'


class ChecksumTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.dest = os.path.join(self.tmpdir.name, 'download')

    def tearDown(self):
        self.tmpdir.cleanup()

    def _write(self, contents):
        with open(self.dest, 'wb') as f:
            f.write(contents)

    def test_verify_checksum_failure_moves_file(self):
        contents = b'incorrect contents'
        self._write(contents)

        with self.assertRaises(ChecksumError) as raised:
            verify_checksum(self.dest, EXPECTED_CHECKSUM)

        self.assertEqual(raised.exception.expected, EXPECTED_CHECKSUM)
        self.assertEqual(raised.exception.movedto, self.dest + '.failed-checksum')
        self.assertFalse(os.path.exists(self.dest))
        with open(raised.exception.movedto, 'rb') as f:
            self.assertEqual(f.read(), contents)

    def test_verify_checksum_nonfatal(self):
        self._write(b'incorrect contents')

        self.assertFalse(verify_checksum(self.dest, EXPECTED_CHECKSUM, fatal=False))
        self.assertFalse(os.path.exists(self.dest))
        self.assertTrue(os.path.isfile(self.dest + '.failed-checksum'))

    def test_verify_checksum_disabled(self):
        contents = b'unchecked contents'
        self._write(contents)

        self.assertTrue(verify_checksum(self.dest, False))
        with open(self.dest, 'rb') as f:
            self.assertEqual(f.read(), contents)

    def test_verify_checksum_missing_expected(self):
        self._write(EXPECTED_CONTENTS)

        with self.assertRaises(ChecksumError) as raised:
            verify_checksum(self.dest, None)

        self.assertEqual(raised.exception.found, EXPECTED_CHECKSUM)
        self.assertIsNone(raised.exception.expected)


class DownloadChecksumTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.dest = os.path.join(self.tmpdir.name, 'download')

    def tearDown(self):
        self.tmpdir.cleanup()

    def _download(self, contents_by_url, checksum, fallback_urls=None):
        requested_urls = []

        async def download_mock(cmd, **kwargs):
            url = cmd[-1]
            requested_urls.append(url)
            with open(self.dest, 'wb') as f:
                f.write(contents_by_url[url])

        with patch.object(shell, 'async_call', side_effect=download_mock), patch.object(
            shell.shutil, 'which', side_effect=lambda command: '/usr/bin/curl' if command == 'curl' else None
        ):
            asyncio.run(
                shell.download(
                    'https://example.com/source',
                    self.dest,
                    fallback_urls=fallback_urls,
                    checksum=checksum,
                )
            )
        return requested_urls

    def test_checksum_failure_tries_fallback_url(self):
        primary = b'incorrect contents'
        fallback_url = 'https://mirror.example.com/source'

        requested_urls = self._download(
            {
                'https://example.com/source': primary,
                fallback_url: EXPECTED_CONTENTS,
            },
            EXPECTED_CHECKSUM,
            [fallback_url],
        )

        self.assertEqual(requested_urls, ['https://example.com/source', fallback_url])
        with open(self.dest + '.failed-checksum', 'rb') as f:
            self.assertEqual(f.read(), primary)

    def test_bad_existing_file_is_replaced(self):
        with open(self.dest, 'wb') as f:
            f.write(b'cached incorrect contents')

        requested_urls = self._download(
            {'https://example.com/source': EXPECTED_CONTENTS},
            EXPECTED_CHECKSUM,
        )

        self.assertEqual(requested_urls, ['https://example.com/source'])
        self.assertTrue(os.path.isfile(self.dest + '.failed-checksum'))

    def test_all_checksum_failures_raise_checksum_error(self):
        fallback_url = 'https://mirror.example.com/source'

        with self.assertRaises(ChecksumError) as raised:
            self._download(
                {
                    'https://example.com/source': b'incorrect primary contents',
                    fallback_url: b'incorrect fallback contents',
                },
                EXPECTED_CHECKSUM,
                [fallback_url],
            )

        self.assertEqual([url for url, error in raised.exception.other_errors], [fallback_url])


if __name__ == '__main__':
    unittest.main()
