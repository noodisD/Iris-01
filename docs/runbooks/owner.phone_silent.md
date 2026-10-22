# owner.phone_silent

**What it means:** The paired phone has delivered nothing for over two days.

**Confirm:** `SELECT max(received_at) FROM sensor_deliveries`; Settings → Android live sensors shows the listener's state.

**Safe fix:** Tell the owner: opening the app resumes collection after a reboot or update; a changed laptop address needs the address QR scanned again.

**Never:** Never rotate the pairing token to fix silence; that disconnects the phone.

See [README](README.md) for action classes and the rules every check follows.
