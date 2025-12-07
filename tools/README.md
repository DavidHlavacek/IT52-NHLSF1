# Telemetry Tools

Record and replay F1 game telemetry for development without the game.

## Recording (Teammate with game)

```bash
# 1. Start recording
python tools/telemetry_recorder.py -o race1.bin -d 60

# 2. Play F1 game (do a lap or two)

# 3. Share the .bin file with team
```

## Replaying (Everyone else)

```bash
# 1. Get .bin file from teammate

# 2. Start your UDP listener / main app in one terminal

# 3. Replay packets in another terminal
python tools/telemetry_replayer.py -i race1.bin

# Options:
#   --loop    Repeat forever
#   --speed 2 Play at 2x speed
```
