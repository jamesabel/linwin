"""Shared TCSS theme for both Windows and Linux TUIs."""

SHARED_CSS = """
Screen {
    background: $surface;
}

/* Force all widgets to use ASCII borders instead of Unicode */
Input {
    border: none;
    height: 1;
    background: $surface;
}
Input:focus {
    border: none;
    background: $boost;
}
DataTable {
    border: ascii $primary;
}
ProgressBar {
    border: ascii $primary;
}

.section-box {
    border: ascii $primary;
    padding: 1 2;
    margin: 1 2;
    height: auto;
}

.section-title {
    text-style: bold;
    color: $text;
    margin-bottom: 1;
}

/* Task status styles */
.task-row {
    height: 1;
    padding: 0 1;
}

.task-status-pending { color: $text-muted; }
.task-status-running { color: $warning; }
.task-status-done { color: $success; }
.task-status-failed { color: $error; }
.task-status-skipped { color: $text-muted; }

/* Log panel */
.log-panel {
    border: ascii $secondary;
    height: 1fr;
    min-height: 8;
}

/* Verify dashboard */
.verify-pass { color: $success; }
.verify-fail { color: $error; }
.verify-warn { color: $warning; }

/* Buttons row */
.button-row {
    height: auto;
    padding: 1 2;
    align-horizontal: center;
}

.button-row .action-link {
    margin: 0 2;
    padding: 0 2;
    text-style: bold;
}

/* Info grid */
.info-grid {
    height: auto;
    grid-size: 2;
    grid-columns: 1fr 2fr;
    padding: 0 1;
}

.info-label {
    text-style: bold;
    color: $text;
}

.info-value {
    color: $text;
}

.info-pass { color: $success; }
.info-fail { color: $error; }
.info-warn { color: $warning; }
"""
