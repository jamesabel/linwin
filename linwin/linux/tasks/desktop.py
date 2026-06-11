"""Desktop shortcut creation for configured optional apps."""

from __future__ import annotations

from ...shared.config import AppEntry
from ...shared.subprocess_runner import LineCallback, run_local
from ...shared.task_result import TaskResult


def _icon_command(app_id: str, desktop_dir: str) -> str:
    """Build the shell command that copies one app's launcher to the desktop.

    Searches snap desktop entries first (firefox_firefox.desktop), then
    exact and suffix matches under /usr/share/applications (the suffix
    glob catches ids like org.gnome.gedit). The xfce-exe-checksum
    metadata marks the launcher trusted so xfdesktop doesn't prompt;
    it is best-effort (gvfs may be unavailable headless).
    """
    return (
        f'DESK="{desktop_dir}"; mkdir -p "$DESK"; src=""; '
        f"for f in /var/lib/snapd/desktop/applications/{app_id}_{app_id}.desktop "
        f"/usr/share/applications/{app_id}.desktop "
        f"/usr/share/applications/*{app_id}.desktop; do "
        '  if [ -f "$f" ]; then src="$f"; break; fi; '
        "done; "
        'if [ -n "$src" ]; then '
        '  dest="$DESK/$(basename "$src")"; '
        '  cp -f "$src" "$dest" && chmod +x "$dest"; '
        '  gio set -t string "$dest" metadata::xfce-exe-checksum '
        '"$(sha256sum "$dest" | cut -d\' \' -f1)" 2>/dev/null || true; '
        "  echo OK; "
        "else echo MISS; fi"
    )


async def create_desktop_icons(apps: list[AppEntry], on_line: LineCallback | None = None) -> TaskResult:
    """Place launcher icons for the configured apps on the user's desktop.

    Apps without a discoverable .desktop entry (e.g. custom apps the
    user installs themselves) are reported but don't fail the step.
    """
    if not apps:
        return TaskResult(ok=True, message="No optional apps selected", skipped=True)

    r = await run_local('xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop"', on_line, timeout=30)
    desktop_dir = r.output.strip().splitlines()[0] if r.output.strip() else "$HOME/Desktop"

    created: list[str] = []
    missing: list[str] = []
    for app in apps:
        result = await run_local(_icon_command(app.id, desktop_dir), on_line, timeout=60)
        if result.success and "OK" in result.output:
            created.append(app.display_name)
        else:
            missing.append(app.display_name)

    parts = []
    if created:
        parts.append(f"desktop shortcuts created: {', '.join(created)}")
    if missing:
        parts.append(f"no launcher found for: {', '.join(missing)}")
    return TaskResult(ok=True, message="; ".join(parts) or "No shortcuts created")
