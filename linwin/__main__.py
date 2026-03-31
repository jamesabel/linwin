"""Entry point for ``python -m linwin``.

Delegates to the Windows or Linux TUI based on the current platform.
"""

import sys


def main() -> None:
    if sys.platform == "win32":
        from linwin.windows.__main__ import main as win_main
        win_main()
    else:
        from linwin.linux.__main__ import main as linux_main
        linux_main()


if __name__ == "__main__":
    main()
