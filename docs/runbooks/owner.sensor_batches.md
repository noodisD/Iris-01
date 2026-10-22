# owner.sensor_batches

**What it means:** Phone batches are staged and wait for the owner's confirmation; nothing in them counts until then.

**Confirm:** `SELECT count(*), min(received_at) FROM sensor_batches WHERE status = 'pending'`.

**Safe fix:** Tell the owner; they confirm or reject on the Sensors screen.

**Never:** Never confirm batches on the owner's behalf.

See [README](README.md) for action classes and the rules every check follows.
