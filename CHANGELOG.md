# Changelog

All notable changes to this project will be documented in this file.

The format is inspired by Keep a Changelog and this project follows Semantic Versioning.

## [0.2.0](https://github.com/luckmattos/flow-st8/compare/flow-st8-v0.1.0...flow-st8-v0.2.0) (2026-08-09)


### Features

* add macOS hotkey tap and text injector ([268307e](https://github.com/luckmattos/flow-st8/commit/268307e8664b5059793735d52748815d316b5785))
* harden autostart and add release automation ([1a55611](https://github.com/luckmattos/flow-st8/commit/1a5561152e541ef2e53cd600a8c11b261d10cde0))
* macOS autostart, microphone and VoiceOver checks ([b11ce74](https://github.com/luckmattos/flow-st8/commit/b11ce742aa8979cffcd863338890b06ef02ac6f7))
* macOS overlay and unified tray ([6ea8c22](https://github.com/luckmattos/flow-st8/commit/6ea8c22b3da31a40cfce08b4c4a2307d1a4f82f5))
* package app and refresh branding ([158bd70](https://github.com/luckmattos/flow-st8/commit/158bd70e365112dc1ca8d89b56f940c59366588d))
* Phase 1 complete - autostart, launcher, GPU detection, AI discoverability ([cfed59e](https://github.com/luckmattos/flow-st8/commit/cfed59ec2811f8ce6205ae08aa64a16a039b41d6))
* pluggable STT backends with MLX on Apple Silicon ([58636f3](https://github.com/luckmattos/flow-st8/commit/58636f354010557a6a5f5e4cb3a6c0e87d4b94b0))
* rebrand tray/overlay icon, animate loading and recording states ([3e1024c](https://github.com/luckmattos/flow-st8/commit/3e1024c6413b470f73e533ac68a804475ed92a25))


### Bug Fixes

* bundle mlx_whisper's data assets, halve the recording badge ([ec4bafc](https://github.com/luckmattos/flow-st8/commit/ec4bafcd6cd5799c645abde5ece093ce64347401))
* GPU load feedback, restricted pt/en detect, reliable autostart ([237f944](https://github.com/luckmattos/flow-st8/commit/237f94424890b71ffabf047fd7d95d74003a0a66))
* macOS recording crash, tray singleton lock, and quit relaunch ([615d41a](https://github.com/luckmattos/flow-st8/commit/615d41a9ca578e46df7c95d97d1865d21ef2b700))
* make the packaged macOS app actually run ([826cdcc](https://github.com/luckmattos/flow-st8/commit/826cdcca96299cc344eed30c421ecddf018eaf9d))
* pin MLX to one thread and require a margin to switch language ([e8da1fe](https://github.com/luckmattos/flow-st8/commit/e8da1fe1cc68966ada957c4956fbaaf9a0376d24))
* port the overlay tooltip/loading redesign to Windows ([c1ac3a8](https://github.com/luckmattos/flow-st8/commit/c1ac3a86f36f11903e552aaf4a74269bd02e9c8d))
* prevent duplicate instances when autostart loads immediately ([7f59688](https://github.com/luckmattos/flow-st8/commit/7f596882ed65af10b329b999002432791a966470))
* prevent Whisper hallucination loops on long transcriptions ([b7ec89b](https://github.com/luckmattos/flow-st8/commit/b7ec89b0cd35f40ea00d1fa287a1fd046860f8e8))
* render the overlay at native Retina resolution with real anti-aliasing ([52c980b](https://github.com/luckmattos/flow-st8/commit/52c980bb83db6b4b468e5a18f8f9b66709ef25d3))
* restore Windows beep and smooth the recording overlay ([1b41f84](https://github.com/luckmattos/flow-st8/commit/1b41f84df9ca186bf053f0b97e7c425f3723186c))
* widen the recording dot's pulse range and amplitude sensitivity ([e8abb1f](https://github.com/luckmattos/flow-st8/commit/e8abb1f1a749a176d5ea076841eb78f144ecabb3))

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
