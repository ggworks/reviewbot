import psutil
import signal


def kill_app():
    for proc in psutil.process_iter():
        try:
            if proc.name() == "uvicorn":
                cmdline = " ".join(proc.cmdline())
                if ".env.cr.local" in cmdline:
                    proc.send_signal(signal.SIGINT)
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass


if __name__ == "__main__":
    kill_app()
