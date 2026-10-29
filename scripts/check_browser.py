"""Exercise the actual page in an isolated Chrome profile, using synthetic data."""

from contextlib import ExitStack
import argparse
import base64
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

from websockets.sync.client import connect


ROOT = Path(__file__).resolve().parents[1]


def until(test, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = test()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("Browser check timed out.")


def run(screenshots=False):
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome:
        raise RuntimeError("Install Chrome or Chromium to run the browser check.")
    processes = []
    previews = Path(tempfile.mkdtemp(prefix="receipt-preview-")) if screenshots else None
    with ExitStack() as stack:
        profile = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="receipt-browser-")))
        log = stack.enter_context(tempfile.TemporaryFile())
        listener = stack.enter_context(socket.socket())
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        env = {key: value for key, value in os.environ.items() if key not in ("QLOO_API_KEY", "QLOO_BASELINE_VERIFIED", "OPENAI_API_KEY", "RECEIPT_ALLOW_LLM_CALLS", "PYTHONPATH")}
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--fd", str(listener.fileno())],
            cwd=ROOT, env=env, pass_fds=(listener.fileno(),), stdout=log, stderr=log)
        processes.append(server)
        def healthy():
            try:
                with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
                    return response.status == 200
            except OSError:
                return False
        try:
            until(healthy)
            browser = subprocess.Popen([
                chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run",
                "--remote-debugging-port=0", "--user-data-dir=" + str(profile), "about:blank",
            ], stdout=log, stderr=log)
            processes.append(browser)
            active = profile / "DevToolsActivePort"
            until(lambda: active.exists() and active.read_text().strip())
            debug_port = active.read_text().splitlines()[0]
            with urlopen("http://127.0.0.1:" + debug_port + "/json/list") as response:
                targets = json.load(response)
            tab = next(target for target in targets if target["type"] == "page")
            with connect(tab["webSocketDebuggerUrl"], open_timeout=10) as websocket:
                errors, serial = [], 0
                def command(method, params=None):
                    nonlocal serial
                    serial += 1
                    websocket.send(json.dumps({"id": serial, "method": method, "params": params or {}}))
                    while True:
                        message = json.loads(websocket.recv(timeout=15))
                        if message.get("method") == "Runtime.exceptionThrown":
                            errors.append(message)
                        if message.get("id") == serial:
                            if "error" in message:
                                raise AssertionError(message["error"])
                            return message.get("result", {})
                def evaluate(expression):
                    result = command("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True})
                    if "exceptionDetails" in result:
                        raise AssertionError(result["exceptionDetails"])
                    return result.get("result", {}).get("value")
                command("Runtime.enable")
                command("Page.enable")
                for width, height in ((1440, 1100), (390, 1000)):
                    command("Emulation.setDeviceMetricsOverride", {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": width < 600})
                    command("Page.navigate", {"url": f"http://127.0.0.1:{port}/"})
                    until(lambda: evaluate("!!document.getElementById('loadSample') && typeof renderAudit === 'function'"))
                    evaluate("document.getElementById('loadSample').click()")
                    until(lambda: evaluate("document.querySelectorAll('.candidate').length === 3 && !document.getElementById('auditButton').disabled"))
                    assert evaluate("document.getElementById('resultMode').textContent") == "DEMO — SYNTHETIC"
                    assert evaluate("document.getElementById('candidateList').textContent.includes('mismatch')")
                    assert evaluate("!document.getElementById('approval').classList.contains('visible')")
                    assert evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Horizontal overflow in result"
                    evaluate("document.getElementById('beginRevision').click()")
                    assert evaluate("document.getElementById('city').disabled")
                    evaluate("document.getElementById('candidates').value = 'Juniper House\\nCobalt Noodles'; document.getElementById('candidates').dispatchEvent(new Event('input')); document.getElementById('auditForm').requestSubmit()")
                    until(lambda: evaluate("document.getElementById('approval').classList.contains('visible')"))
                    evaluate("document.getElementById('approve').click()")
                    until(lambda: evaluate("document.getElementById('issued').classList.contains('visible')"))
                    assert evaluate("JSON.parse(document.getElementById('receiptCode').textContent).approval_recorded")
                    assert evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Horizontal overflow in receipt"
                    evaluate("document.getElementById('candidates').value += '\\nUnknown Place'; document.getElementById('candidates').dispatchEvent(new Event('input'))")
                    assert evaluate("!document.getElementById('approval').classList.contains('visible') && !document.getElementById('issued').classList.contains('visible')")
                    # A failed request must leave old approval inaccessible.
                    evaluate("document.getElementById('city').value = ' '; document.getElementById('auditForm').dispatchEvent(new Event('submit', {cancelable:true}))")
                    until(lambda: evaluate("document.getElementById('error').classList.contains('visible')"))
                    assert evaluate("!document.getElementById('approval').classList.contains('visible')")
                    print(f"PASS {width}px: audit → revision → confirmation → changed-input invalidation → failed-request recovery")
                    evaluate("document.getElementById('tabAgent').click(); document.getElementById('loadSample').click()")
                    until(lambda: evaluate("document.querySelectorAll('#agentTimeline .round-card').length === 2 && !document.getElementById('auditButton').disabled"))
                    assert evaluate("document.getElementById('agentTimeline').textContent.includes('SCRIPTED DEMO')")
                    assert evaluate("document.getElementById('approval').classList.contains('visible') && !document.getElementById('issued').classList.contains('visible')")
                    assert evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                    if previews:
                        evaluate("document.getElementById('agentTimeline').scrollIntoView({block:'start'})")
                        shot = command("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
                        (previews / f"agent-{width}.png").write_bytes(base64.b64decode(shot["data"]))
                    print(f"PASS {width}px: scripted agent → critique → revised audit → explicit review")
                    evaluate("document.getElementById('tabBatch').click(); document.getElementById('loadBatchSample').click(); document.getElementById('runBatch').click()")
                    until(lambda: evaluate("document.querySelectorAll('#batchReport tbody tr').length === 20 && !document.getElementById('runBatch').disabled"))
                    assert evaluate("document.getElementById('batchReport').textContent.includes('DEMO — SYNTHETIC')")
                    assert evaluate("document.querySelectorAll('#batchReport .metric').length === 4")
                    assert evaluate("document.getElementById('batchReport').textContent.includes('10 taste profiles')")
                    assert evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Horizontal overflow in batch report"
                    if previews:
                        evaluate("document.getElementById('batchReport').scrollIntoView({block:'start'})")
                        shot = command("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
                        (previews / f"report-{width}.png").write_bytes(base64.b64decode(shot["data"]))
                    print(f"PASS {width}px: 20-capture batch report → repeat controls → source labels")
                assert not errors, errors
                print("PASS no uncaught browser exceptions")
                if previews:
                    print("Screenshots: " + str(previews))
        finally:
            for process in reversed(processes):
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshots", action="store_true")
    run(parser.parse_args().screenshots)
