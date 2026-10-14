import subprocess
import sys
import unittest


class CommandLineTests(unittest.TestCase):
    def test_module_help_works_without_a_database(self):
        result = subprocess.run(
            [sys.executable, "-m", "cars_data_pipeline", "--help"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--setup-only", result.stdout)


if __name__ == "__main__":
    unittest.main()
