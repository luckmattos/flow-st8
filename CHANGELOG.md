# Changelog

All notable changes to this project will be documented in this file.

The format is inspired by Keep a Changelog and this project follows Semantic Versioning.

## [Unreleased]

## [0.2.0] - 2026-05-08

### Added
- Packaged Windows app build via `flow-st8.spec`.
- Windows setup wizard with hardware detection, model selection, autostart option, existing-install notice, and branded header.
- New flow-st8 logo assets, executable icon, GitHub README banner, and tray icon branding.
- Bottom-right live recording badge using the logo and audio-reactive bars.
- GitHub release build workflow for the setup executable.

### Changed
- Migrated hotkeys to `hold_key` (`Ctrl+Win`) and `toggle_key` (`Ctrl+Win+O`) with config self-healing for old single-key values.
- The app now keeps transcribed text as the latest clipboard item by default.
- README was refreshed for public install, usage, privacy, and packaging guidance.

### Fixed
- PyInstaller packaging now bundles Silero VAD model data required by the frozen app.
- PyInstaller packaging now bundles Whisper assets, including `mel_filters.npz`.
- The setup license screen no longer blocks progress when the checkbox row is clipped.
- Overlay art now respects transparent PNG assets.

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
