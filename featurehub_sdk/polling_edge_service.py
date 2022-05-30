import httpx
import threading
from featurehub_sdk.edge_service import EdgeService


class PollingEdgeService(EdgeService):

    def __init__(self):
        self.cancel = None
        self.poll()

    def get_updates(self):
        with httpx.Client(http2=True) as client:
            # headers = {'Content-Type': 'application/json'}
            resp = client.get(self.url)
            if resp.status_code == httpx.codes.OK:
                self.repository.notify("FEATURES", resp.json())
            else:
                self.repository.notify("FAILED", None)

    def poll_with_interval(self, cancel):
        self.get_updates()
        if not cancel.is_set():
            # call f() again in 60 seconds
            threading.Timer(5, self.poll_with_interval, [cancel]).start()

    f_stop = threading.Event()
    # start calling f now and every 60 sec thereafter
    poll_with_interval(f_stop)

    # stop the thread when needed
    #cancel.set()

    def poll(self):
        self.poll_with_interval(self.cancel)
