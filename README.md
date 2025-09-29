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
    <li>Ken Burns-style motion effects for every image</li>
    <li>Folder ordering with automatic image counts</li>
    <li>Settings stored in <code>settings.json</code> for persistence</li>
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
    All preferences are saved to <code>settings.json</code> by the GUI.
    To enable the optional weather overlay, provide the keys below:
  </p>
  <pre><code>{
  "weather_enabled": false,
  "weather_api_key": "&lt;OpenWeather API key&gt;",
  "weather_location": "&lt;City name or latitude,longitude&gt;",
  "weather_units": "metric"
}</code></pre>
  <p>
    Switch <code>weather_enabled</code> to <code>true</code> after supplying valid values.
    <code>weather_units</code> accepts any unit string supported by your weather provider
    (OpenWeather supports <code>standard</code>, <code>metric</code>, or <code>imperial</code>).
  </p>
</section>

<section>
  <h2>📜 License</h2>
  <p>
    Released under the MIT License — see <a href="LICENSE">LICENSE</a> for details.
  </p>
</section>
