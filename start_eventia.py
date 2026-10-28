import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:8000/'


def main():
    server = subprocess.Popen([
        sys.executable, str(ROOT / 'manage.py'), 'run',
        '--host', '127.0.0.1', '--port', '8000',
    ], cwd=ROOT)
    try:
        for _ in range(40):
            if server.poll() is not None:
                return server.returncode or 1
            try:
                with urllib.request.urlopen(URL, timeout=1) as response:
                    if response.status == 200:
                        print(f'Eventia is ready at {URL}', flush=True)
                        webbrowser.open(URL)
                        return server.wait()
            except (OSError, urllib.error.URLError):
                time.sleep(0.5)
        print('Eventia did not respond. Check whether port 8000 is already in use.', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()


if __name__ == '__main__':
    raise SystemExit(main())
