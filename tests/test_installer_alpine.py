import re
import unittest
from pathlib import Path


class AlpineInstallerTests(unittest.TestCase):
    def test_alpine_dependencies_do_not_require_shadow_or_sudo(self) -> None:
        installer_source = Path("scripts/install.sh").read_text(encoding="utf-8")
        alpine_packages_match = re.search(
            r"alpine\)\s+apk add --no-cache (?P<packages>[^\n]+)",
            installer_source,
        )

        self.assertIsNotNone(alpine_packages_match)
        alpine_packages = alpine_packages_match.group("packages").split()
        self.assertIn("doas", alpine_packages)
        self.assertNotIn("shadow", alpine_packages)
        self.assertNotIn("sudo", alpine_packages)

    def test_alpine_installs_and_uses_doas_policy(self) -> None:
        installer_source = Path("scripts/install.sh").read_text(encoding="utf-8")

        self.assertIn('DOAS_CONF_FILE="/etc/doas.d/aprsbox.conf"', installer_source)
        self.assertIn("install_doas_policy()", installer_source)
        self.assertIn("doas -C \"$DOAS_CONF_FILE\"", installer_source)
        self.assertRegex(
            installer_source,
            r"(?s)install_privilege_policy\(\).*?alpine\)\s+install_doas_policy",
        )

        for service_path in (
            Path("deploy/openrc/aprsbox-core"),
            Path("deploy/openrc/aprsbox-web"),
        ):
            service_source = service_path.read_text(encoding="utf-8")
            self.assertIn('APRSBOX_PRIVILEGED_RUNNER="doas -n"', service_source)
            self.assertNotIn('APRSBOX_PRIVILEGED_RUNNER="sudo -n"', service_source)


if __name__ == "__main__":
    unittest.main()
