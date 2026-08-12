"""Convert existing controlled-demo stereo recordings to compatibility mono.

The original stereo file is retained with a `.stereo.wav` suffix. This only
targets controlled synthetic demo records, leaving live and evidence records
untouched.
"""

from __future__ import annotations

import audioop
import hashlib
from pathlib import Path
import shutil
import wave

from sqlalchemy import text

from app.database import SessionLocal
from app.models import Recording


def main() -> None:
    with SessionLocal() as db:
        targets = list(db.execute(text("""
            SELECT r.id, r.storage_key
            FROM recordings r
            JOIN conversations c ON c.id = r.conversation_id
            JOIN contacts ct ON ct.id = c.contact_id
            WHERE ct.phone LIKE 'demo-%' AND r.channels = 2
        """)))
        for record_id, storage_key in targets:
            path = Path(storage_key)
            backup = path.with_suffix(".stereo.wav")
            if not backup.exists():
                shutil.copyfile(path, backup)
            with wave.open(str(path), "rb") as source:
                params = source.getparams()
                frames = source.readframes(source.getnframes())
            if params.nchannels != 2:
                continue
            mono = audioop.tomono(frames, params.sampwidth, 0.5, 0.5)
            with wave.open(str(path), "wb") as output:
                output.setparams(params._replace(nchannels=1, nframes=0))
                output.writeframes(mono)
            record = db.get(Recording, record_id)
            record.channels = 1
            record.sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        db.commit()
    print(f"Downmixed {len(targets)} controlled demo recording(s).")


if __name__ == "__main__":
    main()
