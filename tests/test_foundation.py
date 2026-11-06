from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from backend.app.config import Settings
from backend.app.db import Database
from backend.app.models import Excerpt, MixPlan, Transition
from backend.app.storage import Storage


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def plan(self):
        return MixPlan("mix", 1, (
            Excerpt("a", 0, 120, 180, 120, 120),
            Excerpt("b", 30, 150, 200, 124, 120),
        ), (Transition("smooth", 32, 16, ("Review phrase alignment",)),))

    def database(self):
        db = Database(self.root / "app.sqlite3")
        db.initialize()
        with db.connection() as con:
            con.execute("INSERT INTO mixes(id) VALUES ('mix')")
            for index, track in enumerate(("a", "b")):
                con.execute("INSERT INTO tracks(id,content_hash,original_name,storage_name,metadata_json) VALUES (?,?,?,?,?)",
                            (track, "same-content", track + ".mp3", track, "{}"))
                con.execute("INSERT INTO mix_tracks VALUES (?,?,?)", ("mix", track, index))
        return db

    def test_plan_persists_across_connections_and_revisions(self):
        db = self.database()
        plan = self.plan()
        db.save_plan(plan)
        self.assertEqual(Database(db.path).load_plan("mix", 1), plan)
        changed = replace(plan, revision=2, transitions=(Transition("eq_cut", 8, 4),))
        db.save_plan(changed)
        self.assertEqual(db.load_plan("mix", 1), plan)
        self.assertEqual(db.load_plan("mix", 2), changed)
        with self.assertRaises(ValueError):
            db.save_plan(plan)

    def test_members_cannot_be_dropped(self):
        db = self.database()
        with self.assertRaises(ValueError):
            db.save_plan(replace(self.plan(), excerpts=self.plan().excerpts[:1], transitions=()))
        with db.connection() as con:
            self.assertEqual(con.execute("SELECT requested_revision FROM mixes").fetchone()[0], 0)

    def test_bounds_nonfinite_and_consuming_overlaps_rejected(self):
        plan = self.plan()
        for bad in (replace(plan.excerpts[0], source_out=181),
                    replace(plan.excerpts[0], source_bpm=float("nan")),
                    replace(plan.excerpts[0], target_bpm=0)):
            with self.assertRaises(ValueError):
                replace(plan, excerpts=(bad, plan.excerpts[1])).validate()
        with self.assertRaises(ValueError):
            replace(plan, transitions=(Transition("smooth", 120, 32),)).validate()

    def test_storage_rejects_traversal_and_cleans_temporary_files(self):
        storage = Storage(self.root)
        storage.initialize()
        for name in ("../secret", "..\\secret", "C:secret", "/absolute", ".."):
            with self.assertRaises(ValueError):
                storage.path("uploads", name)
        self.assertNotEqual(storage.new_upload_path(), storage.new_upload_path())
        with storage.temporary_directory() as path:
            (path / "partial.wav").write_bytes(b"partial")
        self.assertFalse(path.exists())

    def test_local_only_configuration(self):
        with self.assertRaises(ValueError):
            Settings(host="0.0.0.0")
        with self.assertRaises(ValueError):
            Settings(heavy_workers=2)


if __name__ == "__main__":
    unittest.main()
