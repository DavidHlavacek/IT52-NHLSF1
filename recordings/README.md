# Telemetry Recordings

Store recorded F1 telemetry `.bin` files here.

## Record

```bash
python tools/telemetry_recorder.py -o recordings/spa_60sec.bin -d 60
```

## Replay

```bash
python tools/telemetry_replayer.py -i recordings/spa_60sec.bin
python tools/telemetry_replayer.py -i recordings/spa_60sec.bin --loop
python tools/telemetry_replayer.py -i recordings/spa_60sec.bin --speed 2
```
