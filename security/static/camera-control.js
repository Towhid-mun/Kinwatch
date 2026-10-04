// Shared by camview.html and capture.html: checks whether the monitor is
// currently holding the camera(s), and if so, offers a one-click "stop it
// and load the live view" control instead of requiring an SSH session and
// a manual `sudo systemctl stop security-monitor`. Calls
// loadStreams() once the camera is confirmed free (either it already was,
// or the pause button just freed it).
window.SecurityCameraControl = {
  setup: function (loadStreams) {
    var statusEl = document.getElementById('monitorStatus');
    var pauseBtn = document.getElementById('pauseMonitorBtn');
    var resumeBtn = document.getElementById('resumeMonitorBtn');
    var pausedByUs = false;

    function setStatus(active) {
      statusEl.textContent = active ? 'Monitor: running' : 'Monitor: stopped';
      statusEl.className = 'status-badge ' + (active ? 'status-badge-active' : 'status-badge-inactive');
      pauseBtn.style.display = active ? 'inline-block' : 'none';
      resumeBtn.style.display = active ? 'none' : 'inline-block';
    }

    function refreshStatus() {
      return fetch('/camera/monitor-status')
        .then(function (resp) { return resp.json(); })
        .then(function (body) { setStatus(body.active); return body.active; })
        .catch(function () { return null; });
    }

    pauseBtn.addEventListener('click', function () {
      pauseBtn.disabled = true;
      pauseBtn.textContent = 'Stopping monitor...';
      fetch('/camera/pause-monitor', {method: 'POST'})
        .then(function (resp) {
          if (!resp.ok) {
            return resp.json().catch(function () { return {}; }).then(function (body) {
              alert('Failed to stop monitor: ' + (body.error || resp.status));
            });
          }
          pausedByUs = true;
          setStatus(false);
          loadStreams();
        })
        .finally(function () {
          pauseBtn.disabled = false;
          pauseBtn.textContent = 'Stop monitor & view cameras';
        });
    });

    resumeBtn.addEventListener('click', function () {
      resumeBtn.disabled = true;
      resumeBtn.textContent = 'Starting monitor...';
      fetch('/camera/resume-monitor', {method: 'POST'})
        .then(function (resp) {
          if (!resp.ok) {
            return resp.json().catch(function () { return {}; }).then(function (body) {
              alert('Failed to start monitor: ' + (body.error || resp.status));
            });
          }
          pausedByUs = false;
          setStatus(true);
        })
        .finally(function () {
          resumeBtn.disabled = false;
          resumeBtn.textContent = 'Resume monitoring';
        });
    });

    // A reminder, not a hard block - if you paused monitoring to look at
    // the camera, it's easy to forget to turn it back on when you navigate
    // away.
    window.addEventListener('beforeunload', function (event) {
      if (pausedByUs) {
        event.preventDefault();
        event.returnValue = '';
      }
    });

    refreshStatus().then(function (active) {
      if (active === false) loadStreams();
    });
  }
};
