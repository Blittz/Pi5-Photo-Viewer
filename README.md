<div align="center">
  <img src="assets/logo.png" alt="Pi5 Photo Viewer Logo" height="120">
  <h1>Pi5 Photo Viewer</h1>
  <p>
    A fullscreen Raspberry&nbsp;Pi 5 slideshow that keeps photo folders refreshed,
    adds smooth Ken Burns motion, and stays friendly on touch displays.
  </p>
</div>

<hr>

<section>
  <h2>✨ Features</h2>
  <ul>
    <li>Fullscreen slideshow with shuffle and adjustable duration</li>
    <li>Visible 30-second startup countdown using saved settings; cancel it with
      “Cancel auto-start” or by interacting with settings. “Start Slideshow” starts
      immediately. The countdown runs once per application launch.</li>
    <li>Ken Burns-style motion effects for every image</li>
    <li>Folder ordering with automatic image counts</li>
    <li>Settings stored in <code>settings.json</code> for persistence</li>
    <li>Optional night schedule that pauses the slideshow and shows a black screen</li>
    <li>Weather overlay fields (API key, location, units) ready for configuration</li>
  </ul>
</section>

<section>
  <h2>🚀 Quick Start</h2>
  <ol>
    <li><code>git clone https://github.com/Blittz/Pi5-Photo-Viewer.git</code></li>
    <li><code>cd Pi5-Photo-Viewer</code></li>
    <li><code>python3 -m venv venv</code></li>
    <li><code>source venv/bin/activate</code></li>
    <li><code>pip install -r requirements.txt</code></li>
    <li><code>python3 main.py</code></li>
  </ol>
</section>

<section>
  <h2>⚙️ Configuration</h2>
  <p>
    If a selected photo folder is unavailable or no readable images are found,
    the settings window stays open with a message. Reconnect the folder or choose
    another, then click “Start Slideshow”. Returning from a slideshow does not
    restart the countdown.
  </p>
  <p>
    All preferences are saved locally to <code>settings.json</code> by the GUI.
    On a new installation, copy <code>settings.example.json</code> to
    <code>settings.json</code> and select photo folders. Local settings, legacy
    <code>config.json</code>, credentials, and photo files are excluded from Git.
    Enable the optional weather overlay with <code>weather_enabled: true</code>.
    Current observations come from NWS station KMFR (Medford Airport), in °F and mph.
    No API key is needed; saved OpenWeather settings remain stored but unused.
  </p>
  <p>
    The experimental Quiet sidebar reserves 36% of the display on the right for a
    stationary clock, date, weather, and solar times. Photos fit the remaining area
    without stretching; motion and transitions are clipped to that area. Weather
    icons are drawn locally as scalable line art, including day/night and unknown
    conditions, with no weather-image downloads. The folder/date caption stays at
    the bottom of the photo area. Existing font controls scale the sidebar and
    caption; long weather text wraps. The slideshow cursor hides after three seconds
    without activity and reappears immediately on movement or input, including in
    nighttime mode. Settings retain their normal cursor. Very small windows can scroll the sidebar
    rather than hiding essential readings. Observation/fetch times and stale or
    failed-update indicators remain visible in the information group.
  </p>
  <p>
    Requests time out after 20 seconds. Successful requests refresh every five minutes;
    failures retain the last reading, mark it STALE, and retry after 10, 20, 40, then
    60 minutes. Success resets this interval. Observations older than 90 minutes are
    also marked STALE, even when fetching succeeds. Observation time and fetch time
    are displayed separately in America/Los_Angeles, including daylight saving time.
    Missing fields are omitted or labeled unavailable; feels-like uses NWS heat index
    or wind chill when available. Icons use NWS rather than OpenWeather.
  </p>
  <p>
    Sunrise and sunset are calculated locally for KMFR (42.37503, -122.87696) using
    NOAA solar equations and standard refraction. Calculations refresh within one
    minute of the Pacific date changing, even when the weather service is unavailable.
    These are approximate horizon times; nearby terrain and atmospheric conditions
    can change the visible sunrise or sunset. No additional packages or services
    are required for the calculations.
  </p>
  <p>
    A quiet health indicator stays invisible while checks are healthy. Confirmed
    faults add a static thin red outline around the entire slideshow window and a
    short warning below the observation information. Night mode dims both using
    the saved night display brightness. Recovery clears the indicator automatically.
    Read-only worker processes check the expected CIFS mount at
    <code>~/server/Shared</code>, readability of selected folders on that mount,
    and the system service <code>discord-bot.service</code> every 30 seconds.
    Empty folders and a lack of new photos are healthy. Each system probe is
    bounded to six seconds, overlapping probes are prevented, and two consecutive
    failed samples confirm a warning. Service status does not establish a working
    Discord connection; the viewer never contacts Discord or restarts services.
    Weather health uses the existing request-error and 90-minute observation-age
    rules, with a 90-second initial-data grace period and the same two-sample
    debounce. No additional weather requests are made. Only health transitions
    are logged, without credentials, paths, or message contents.
  </p>
  <p>
    To schedule overnight blackouts, enable <em>Night Mode Schedule</em> in the GUI and set
    start and end times (24-hour <code>HH:MM</code> format). The slideshow pauses at the
    start time, switches to a separate full-screen night information display, and
    restores the daytime sidebar and slideshow automatically at the end time.
    The night display uses almost-black backgrounds, dim warm-gray text, and
    subdued amber line icons, with the clock/weather above four information tiles.
    Clock, NWS updates, stale/error status, local solar-date refresh, and idle cursor
    hiding continue while photos and captions are hidden. Overnight schedules can
    cross midnight. <code>night_display_brightness</code> (5–100%, default 30%) is
    saved by the “Night display brightness” slider and affects text/icons only;
    it never changes monitor or system brightness.
  </p>
</section>

<section>
  <h2>📜 License</h2>
  <p>
    Released under the MIT License — see <a href="LICENSE">LICENSE</a> for details.
  </p>
</section>
