import os
import time

deleted_count = 0
for dp, _, files in os.walk("music"):
    for f in files:
        if f.endswith(".mp3"):
            p = os.path.join(dp, f)
            removed = False
            for attempt in range(5):
                try:
                    os.remove(p)
                    print(f"DELETED LEGACY BGM: {p}")
                    deleted_count += 1
                    removed = True
                    break
                except Exception as e:
                    time.sleep(0.5)
            if not removed:
                print(f"WARNING: Could not remove {p}")

print(f"\nPurged total {deleted_count} legacy background music tracks.")
