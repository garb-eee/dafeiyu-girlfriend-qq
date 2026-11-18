from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install_dsh_github.py"


class DshGithubInstallerTests(unittest.TestCase):
    def test_installs_read_only_plugin_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            profile = Path(folder) / "profile"
            profile.mkdir()
            (profile / "package.json").write_text(
                json.dumps(
                    {
                        "name": "test-profile",
                        "private": True,
                        "dependencies": {},
                        "dsh": {"profile": {"bundles": []}},
                    }
                ),
                encoding="utf-8",
            )
            (profile / "cordis.patch.yml").write_text(
                "- id: dsh-onebot\n  config:\n    workspacePath: C:\\old\n",
                encoding="utf-8",
            )

            command = [
                sys.executable,
                str(INSTALLER),
                "--profile",
                str(profile),
                "--workspace",
                r"D:\DafeiyuGirlfriend\qqgf",
                "--gh-path",
                "gh",
                "--git-path",
                "git",
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)
            subprocess.run(command + ["--check"], check=True, capture_output=True, text=True)

            package = json.loads((profile / "package.json").read_text(encoding="utf-8"))
            self.assertIn("dsh-github", package["dependencies"])
            self.assertIn("dsh-github", package["dsh"]["profile"]["bundles"])

            patch = (profile / "cordis.patch.yml").read_text(encoding="utf-8")
            self.assertEqual(patch.count("- id: github"), 1)
            self.assertIn("allowWrite: false", patch)
            self.assertIn(r"workspacePath: D:\DafeiyuGirlfriend\qqgf", patch)

            plugin = profile / "_local-plugins" / "dsh-github" / "lib" / "index.js"
            self.assertTrue(plugin.is_file())
            source = plugin.read_text(encoding="utf-8")
            self.assertIn("allowWrite: Schema.boolean().default(false)", source)
            self.assertIn("writeGuard(config, args, 'external_side_effect', 'cloning a repository')", source)
            self.assertIn("...(target ? [assertRepo(target)] : [])", source)
            self.assertNotIn("gh(['repo', 'view', ...repoArgs", source)
            self.assertNotIn("openIssueCount", source)

    def test_ghcr_workflow_and_portable_override_exist(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "publish-ghcr.yml").read_text(
            encoding="utf-8"
        )
        override = (ROOT / "compose.portable.override.yaml").read_text(encoding="utf-8")
        self.assertIn("packages: write", workflow)
        self.assertIn("docker/build-push-action", workflow)
        self.assertIn("ghcr.io/garb-eee/dafeiyu-girlfriend-qq:latest", override)


if __name__ == "__main__":
    unittest.main()
