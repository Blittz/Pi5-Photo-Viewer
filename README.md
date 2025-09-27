<p align="center">
  <img src="https://raw.githubusercontent.com/Blittz/Pi5-Photo-Viewer/main/assets/logo.png" height="120">
</p>

<h1 align="center">Pi5 Photo Viewer</h1>

<p align="center">
  A fullscreen, motion-enhanced, touchscreen-friendly photo slideshow app built for Raspberry Pi 5.<br>
  Featuring auto-refreshing folders, Ken Burns effects, image overlay info, and a simple GUI.
</p>

<p align="center">
  <img src="https://img.shields.io/github/stars/Blittz/Pi5-Photo-Viewer?style=flat-square">
  <img src="https://img.shields.io/github/last-commit/Blittz/Pi5-Photo-Viewer?style=flat-square">
  <img src="https://img.shields.io/badge/made%20for-Raspberry%20Pi-red?style=flat-square">
</p>

---

## ✨ Features

- 🖼️ Fullscreen photo slideshow
- 🔁 Auto-refreshes folders for new images
- 🎞️ Smooth pan/zoom (Ken Burns style)
- 🔀 Shuffle mode
- ⏱️ Adjustable image duration
- 🧠 Remembers last used folders and settings
- 🎛️ GUI for control — no config files required
- 🌤️ Weather + overlay support (coming soon)
- 🕒 Scheduling + dimming (coming soon)

---

## 📸 Screenshots

> _These are placeholder paths — upload your screenshots to `/assets` and link them here._

<p align="center">
  <img src="assets/screenshot1.png" width="700">
  <br>
  <img src="assets/screenshot2.png" width="700">
</p>

---

## 🚀 Getting Started

### Requirements:
- Raspberry Pi 5 (16GB recommended)
- Raspberry Pi OS 64-bit Desktop
- Python 3.11+
- Virtualenv (optional but recommended)

### Setup

```bash
git clone https://github.com/Blittz/Pi5-Photo-Viewer.git
cd Pi5-Photo-Viewer
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 main.py
