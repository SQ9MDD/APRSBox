import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.https_files import (
    HTTPS_CA_CHAIN_FILENAME,
    HTTPS_CERTIFICATE_FILENAME,
    HTTPS_PRIVATE_KEY_FILENAME,
    https_file_status,
    save_https_file,
)


class HttpsFileTests(unittest.TestCase):
    def test_status_requires_certificate_and_private_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ssl_dir = Path(temp_dir) / "ssl"
            self.assertEqual(
                https_file_status(ssl_dir),
                {
                    "certificate_available": False,
                    "private_key_available": False,
                    "ca_chain_available": False,
                    "https_ready": False,
                },
            )

            save_https_file(ssl_dir, HTTPS_CERTIFICATE_FILENAME, b"certificate")
            self.assertFalse(https_file_status(ssl_dir)["https_ready"])

            save_https_file(ssl_dir, HTTPS_PRIVATE_KEY_FILENAME, b"private-key", private=True)
            self.assertFalse(https_file_status(ssl_dir)["https_ready"])
            with patch("app.services.https_files.ssl.SSLContext.load_cert_chain"):
                self.assertTrue(https_file_status(ssl_dir)["https_ready"])

    def test_uploads_use_fixed_filenames_and_private_key_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ssl_dir = Path(temp_dir) / "ssl"
            save_https_file(ssl_dir, HTTPS_CERTIFICATE_FILENAME, b"certificate")
            save_https_file(ssl_dir, HTTPS_PRIVATE_KEY_FILENAME, b"private-key", private=True)
            save_https_file(ssl_dir, HTTPS_CA_CHAIN_FILENAME, b"ca-chain")

            self.assertEqual((ssl_dir / "aprsbox.crt").read_bytes(), b"certificate")
            self.assertEqual((ssl_dir / "aprsbox.key").read_bytes(), b"private-key")
            self.assertEqual((ssl_dir / "aprsbox-ca-chain.crt").read_bytes(), b"ca-chain")
            self.assertEqual((ssl_dir / "aprsbox.key").stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
