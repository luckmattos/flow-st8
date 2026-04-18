# Changelog

All notable changes to this project will be documented in this file.

The format is inspired by Keep a Changelog and this project follows Semantic Versioning.

## [Unreleased]

### Fixed
- Whisper hallucination loop on long transcriptions: added `condition_on_previous_text=False`, `logprob_threshold=-1.0`, simplified temperature to `(0.0,)`, trailing-silence trim, and repetition-loop post-processing.

## [0.1.0] - 2026-04-14

### Added
- Persistent autostart toggle saved to `%APPDATA%\\flow-st8\\config.toml`.
- Rotating log file at `%APPDATA%\\flow-st8\\flow-st8.log` for startup diagnostics.
- Lazy preload for Silero VAD during app startup.
- Project versioning via `VERSION` and `version.py`.
- GitHub Actions CI and tag-based release workflow.

### Changed
- Autostart now prefers Task Scheduler and falls back to the per-user Startup folder when Windows denies scheduled-task creation.
- Startup fallback launcher now runs hidden, uses the exact `pythonw.exe`, and starts after a shorter 10-second delay.
- Internal `schtasks` commands now run without flashing terminal windows.

### Fixed
- Autostart state toggled from the tray is now persisted and no longer gets reverted on the next app launch.
- Startup-folder VBS generation now escapes the launch command correctly.
