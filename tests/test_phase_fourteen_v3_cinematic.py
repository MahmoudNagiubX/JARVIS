from __future__ import annotations

from unittest.mock import patch

from jarvis.desktop.instance import SingleInstanceLock
from jarvis.desktop.lifecycle import JarvisDesktopLifecycle


def test_second_desktop_launch_reopens_the_existing_local_app(tmp_path) -> None:
    lock_path = tmp_path / "run" / "instance.lock"
    first_lock = SingleInstanceLock(lock_path)
    assert first_lock.acquire()
    first_lock.publish_metadata(app_url="http://127.0.0.1:54321/app")

    second = JarvisDesktopLifecycle(instance_lock=SingleInstanceLock(lock_path))
    opened: list[str] = []
    with patch("jarvis.desktop.lifecycle.webbrowser.open", side_effect=lambda url: opened.append(url) or True):
        assert second.open_existing_hud()

    assert opened == ["http://127.0.0.1:54321/app"]
    first_lock.release()


def test_second_desktop_launch_rejects_non_loopback_handoff_urls(tmp_path) -> None:
    lock_path = tmp_path / "run" / "instance.lock"
    first_lock = SingleInstanceLock(lock_path)
    assert first_lock.acquire()
    first_lock.publish_metadata(app_url="https://example.invalid/app")

    second = JarvisDesktopLifecycle(instance_lock=SingleInstanceLock(lock_path))
    with patch("jarvis.desktop.lifecycle.webbrowser.open") as open_browser:
        assert not second.open_existing_hud()

    open_browser.assert_not_called()
    first_lock.release()
