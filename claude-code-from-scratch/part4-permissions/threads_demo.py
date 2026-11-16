"""Threads in a few lines: four jobs that each wait 0.3 seconds, run side by side."""
import time
from concurrent.futures import ThreadPoolExecutor


def wait(seconds):
    time.sleep(seconds)        # like a tool waiting for a disk or a web page
    return seconds


start = time.perf_counter()
with ThreadPoolExecutor(max_workers=8) as pool:
    results = list(pool.map(wait, [0.3, 0.3, 0.3, 0.3]))
print(results, f"in {time.perf_counter() - start:.2f} s")
