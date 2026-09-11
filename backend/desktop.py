import threading
import time
import webbrowser
import uvicorn


def open_browser():
    time.sleep(1.4)
    webbrowser.open("http://127.0.0.1:8765")


if __name__ == "__main__":
    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run("app.main:app", host="127.0.0.1", port=8765, log_level="warning")
