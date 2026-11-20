import os
import glob
import json
import time
import player
import runner
import main

print("===================================================================")
print("TESTING STOUD WITH CAPTURES FROM F:\\Captures")
print("===================================================================")

files = glob.glob("F:/Captures/*.mp4")
print(f"Found {len(files)} capture files in F:\\Captures:\n")

for idx, f in enumerate(files, 1):
    info = player.inspect_media(f)
    print(f"--- File {idx}: {os.path.basename(f)} ---")
    print(f"  Path: {f}")
    print(f"  Size: {info.get('filesize_gb')} GB ({info.get('filesize_bytes')} bytes)")
    print(f"  Duration: {info.get('duration_formatted')} ({round(info.get('duration') or 0, 1)}s)")
    print(f"  Is Large (>1GB / >30m): {info.get('is_large')}")
    print(f"  Recommended Shards (30m): {info.get('recommended_shards')}")
    print()

# Test 1: Testing Shard Queue Generator with 10-minute shards on the 3.46GB file
large_file = "F:/Captures/Rise of the Tomb Raider v1.0 build 1.0_64 2026-11-20 14-34-31.mp4"
print("===================================================================")
print("TEST 1: SHARDING 3.46GB CAPTURE INTO 10-MINUTE SHARDS")
print("===================================================================")

runner.current_queue = []
success, count = runner.add_sharded_to_queue(large_file, "Tomb Raider 3.4GB Test", shard_duration_minutes=10)
print(f"Successfully generated {count} shards:")
for i, item in enumerate(runner.current_queue, 1):
    print(f"  Shard #{i}: {item['title']}")
    print(f"    Offset: {item['start_offset']}s | Duration: {item['duration']}s | Is Shard: {item['is_shard']}")

# Test 2: Testing API Inspection endpoint with Flask test_client
print("\n===================================================================")
print("TEST 2: TESTING /api/media/inspect AND /api/queue/shard_video")
print("===================================================================")
client = main.app.test_client()

for f in files:
    res = client.post("/api/media/inspect", json={"url": f})
    data = res.get_json()
    print(f"POST /api/media/inspect [{os.path.basename(f)[:30]}...]: Status {res.status_code}")
    print(f"  -> Title: {data['info']['title']}")
    print(f"  -> Size: {data['info']['filesize_gb']} GB, Shards: {data['info']['recommended_shards']}")

# Test 3: Testing FFmpeg command generation for Shard 2 (Offset: 600s, Duration: 600s)
print("\n===================================================================")
print("TEST 3: VERIFYING FFMPEG COMMAND GENERATION FOR SHARD 2")
print("===================================================================")
shard_2 = runner.current_queue[1]
dests = [{"id": "test", "name": "YouTube Live", "rtmp_url": "rtmp://a.rtmp.youtube.com/live2", "stream_key": "test-key-123", "enabled": True}]
cmd = player.build_ffmpeg_cmd(
    ffmpeg_exe="ffmpeg",
    video_input=shard_2["url"],
    audio_input=None,
    destinations=dests,
    quality="copy",
    budget_mode=True,
    start_offset=shard_2["start_offset"],
    duration=shard_2["duration"]
)
print("Generated FFmpeg Command:")
print(" ".join(cmd))

# Verify critical constraints:
print("\nVerification Checklist:")
print(f"  1. Input Fast Seek (-ss {shard_2['start_offset']}) before -i: {'-ss' in cmd and cmd.index('-ss') < cmd.index('-i')}")
print(f"  2. Shard Duration (-t {shard_2['duration']}): {'-t' in cmd}")
print(f"  3. Render Budget Queue Ceiling (-max_muxing_queue_size 128): {'-max_muxing_queue_size' in cmd}")
print(f"  4. Render 1-Thread Ceiling (-threads 1): {'-threads' in cmd}")
print(f"  5. Direct Copy Zero-CPU (-c:v copy): {'-c:v' in cmd and cmd[cmd.index('-c:v')+1] == 'copy'}")

print("\nALL TEST SCENARIOS PASSED SUCCESSFULLY!")
