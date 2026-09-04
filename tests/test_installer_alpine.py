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

    def test_installer_and_updater_treat_uvicorn_accelerators_as_optional_wheels(self) -> None:
        requirements = Path("requirements.txt").read_text(encoding="utf-8")
        accelerator_requirements = Path("requirements-accelerators.txt").read_text(encoding="utf-8")
        installer_source = Path("scripts/install.sh").read_text(encoding="utf-8")
        updater_source = Path("scripts/update.sh").read_text(encoding="utf-8")
        dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

        self.assertNotIn("uvloop", requirements)
        self.assertNotIn("httptools", requirements)
        self.assertIn("uvloop==0.22.1", accelerator_requirements)
        self.assertIn("httptools==0.6.4", accelerator_requirements)
        self.assertIn('"$VENV_DIR/bin/pip" install -r "$STAGING_APP_DIR/requirements.txt"', installer_source)
        self.assertIn('"$VENV_DIR/bin/pip" install --only-binary=:all: -r "$accelerator_requirements"', installer_source)
        self.assertIn('"$NEW_VENV_DIR/bin/pip" install -r "$STAGING_APP_DIR/requirements.txt"', updater_source)
        self.assertIn('"$runtime_venv_dir/bin/pip" install --only-binary=:all: -r "$accelerator_requirements"', updater_source)
        self.assertIn('pip install --only-binary=:all: -r /opt/aprsbox/app/requirements-accelerators.txt', dockerfile)
        self.assertIn("BACKUP_RETENTION_COUNT", updater_source)
        self.assertIn('prune_database_backups "$backup_path"', updater_source)

    def test_updater_installs_missing_system_prerequisites_without_upgrading_the_host(self) -> None:
        updater_source = Path("scripts/update.sh").read_text(encoding="utf-8")

        self.assertIn("ensure_system_prerequisites", updater_source)
        self.assertIn("apt-get update", updater_source)
        self.assertIn("python3 python3-venv python3-pip git rsync ca-certificates", updater_source)
        self.assertIn("apk add --no-cache python3 py3-pip py3-virtualenv git rsync ca-certificates", updater_source)
        self.assertNotIn("apt-get upgrade", updater_source)


if __name__ == "__main__":
    unittest.main()
