import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from config import get_openai_api_key, load_env_file


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.env = Path(self.dir.name) / ".env"
        patcher = mock.patch.dict(os.environ, {}, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.dir.cleanup)

    def write(self, text, mode=0o600):
        self.env.write_text(text)
        self.env.chmod(mode)

    def test_reads_key_from_env_file(self):
        self.write("# comment\nOPENAI_API_KEY='sk-test-123'\n")
        self.assertEqual(get_openai_api_key(self.env), "sk-test-123")

    def test_environment_variable_wins(self):
        self.write("OPENAI_API_KEY=sk-from-file\n")
        os.environ["OPENAI_API_KEY"] = "sk-from-env"
        self.assertEqual(get_openai_api_key(self.env), "sk-from-env")

    def test_missing_or_placeholder_key_raises(self):
        with self.assertRaises(RuntimeError):
            get_openai_api_key(self.env)  # no file
        self.write("OPENAI_API_KEY=sk-your-key-here\n")
        with self.assertRaises(RuntimeError):
            get_openai_api_key(self.env)

    def test_warns_when_file_is_world_readable(self):
        self.write("OPENAI_API_KEY=sk-test\n", mode=0o644)
        with self.assertWarns(UserWarning):
            load_env_file(self.env)


if __name__ == "__main__":
    unittest.main()
