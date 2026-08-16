import unittest
from pathlib import Path


class HttpsServiceDeploymentTests(unittest.TestCase):
    def test_redirect_service_preserves_path_with_permanent_redirect(self) -> None:
        redirect_source = Path("scripts/http-redirect.py").read_text(encoding="utf-8")

        self.assertIn("self.send_response(308)", redirect_source)
        self.assertIn('f"https://{host}{self.path}"', redirect_source)
        for method in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"):
            self.assertIn(f"do_{method} = redirect", redirect_source)

    def test_systemd_uses_uvicorn_tls_and_redirect_capabilities(self) -> None:
        web_service = Path("deploy/systemd/aprsbox-web.service").read_text(encoding="utf-8")
        core_service = Path("deploy/systemd/aprsbox-core.service").read_text(encoding="utf-8")
        redirect_service = Path("deploy/systemd/aprsbox-http-redirect.service").read_text(encoding="utf-8")
        web_launcher = Path("scripts/start-web.sh").read_text(encoding="utf-8")

        self.assertIn("AmbientCapabilities=CAP_NET_BIND_SERVICE", web_service)
        self.assertIn("scripts/start-web.sh", web_service)
        self.assertIn("--port 443", web_launcher)
        self.assertIn('--ssl-certfile "$SSL_DIR/aprsbox.crt"', web_launcher)
        self.assertIn('--ssl-keyfile "$SSL_DIR/aprsbox.key"', web_launcher)
        self.assertIn("--port 80", web_launcher)
        self.assertIn("-m uvicorn app.core_main:app", core_service)
        self.assertIn("AmbientCapabilities=CAP_NET_BIND_SERVICE", redirect_service)
        self.assertNotIn("gunicorn", web_service + core_service)

    def test_openrc_uses_uvicorn_tls_and_redirect_capabilities(self) -> None:
        web_service = Path("deploy/openrc/aprsbox-web").read_text(encoding="utf-8")
        core_service = Path("deploy/openrc/aprsbox-core").read_text(encoding="utf-8")
        redirect_service = Path("deploy/openrc/aprsbox-http-redirect").read_text(encoding="utf-8")

        self.assertIn('capabilities="^cap_net_bind_service"', web_service)
        self.assertIn("scripts/start-web.sh", web_service)
        self.assertIn("-m uvicorn app.core_main:app", core_service)
        self.assertIn('capabilities="^cap_net_bind_service"', redirect_service)
        self.assertNotIn("gunicorn", web_service + core_service)

    def test_installer_and_updater_install_redirect_service_for_both_init_systems(self) -> None:
        installer = Path("scripts/install.sh").read_text(encoding="utf-8")
        updater = Path("scripts/update.sh").read_text(encoding="utf-8")

        self.assertIn('$SYSTEMD_DEPLOY_DIR/aprsbox-http-redirect.service', installer)
        self.assertIn('$OPENRC_DEPLOY_DIR/aprsbox-http-redirect', installer)
        self.assertIn('$APP_DIR/deploy/systemd/aprsbox-http-redirect.service', updater)
        self.assertIn('$APP_DIR/deploy/openrc/aprsbox-http-redirect', updater)
        self.assertIn("rc-update add aprsbox-http-redirect default", installer)
        self.assertIn("rc-update add aprsbox-http-redirect default", updater)

    def test_new_restart_helpers_migrate_units_when_launched_by_old_updater(self) -> None:
        systemd_helper = Path("scripts/update-web-restart.sh").read_text(encoding="utf-8")
        restart_helper = Path("scripts/restart-services.sh").read_text(encoding="utf-8")
        requirements = Path("requirements.txt").read_text(encoding="utf-8")

        self.assertIn("deploy/systemd/aprsbox-http-redirect.service", systemd_helper)
        self.assertIn("systemctl daemon-reload", systemd_helper)
        self.assertIn("systemctl restart aprsbox-core.service", systemd_helper)
        self.assertIn("systemctl restart aprsbox-http-redirect.service", systemd_helper)
        self.assertIn("deploy/openrc/aprsbox-http-redirect", restart_helper)
        self.assertIn("rc-update add aprsbox-http-redirect default", restart_helper)
        self.assertIn("gunicorn==23.0.0", requirements)


if __name__ == "__main__":
    unittest.main()
