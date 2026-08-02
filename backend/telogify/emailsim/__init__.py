"""emailsim: a measured (not guessed) model of how Gmail actually renders the digest email.

Every prior claim about Gmail's CSS support and dark-mode color inversion in this project was
either a hand-tested hypothesis or an emulation (Chromium's `prefers-color-scheme`, which Gmail's
mobile apps ignore entirely). This package replaces guessing with measurement: send a probe email
of known color swatches and known CSS properties to real Gmail, screenshot it, and derive the
actual transfer function and support matrix from the pixels.

Two things only, both measured: `darkmode` (a color LUT) and `support` (a binary CSS matrix).
Not a layout engine, not a font-metrics engine -- see the project plan for the stated ceiling.
"""
