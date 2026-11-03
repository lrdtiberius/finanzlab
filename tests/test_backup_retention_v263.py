import tempfile
import unittest
from pathlib import Path

from app.infrastructure.repository import BACKUP_RETENTION_LIMIT, Repository


class BackupRetentionV263Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "planner.db"
        self.repo = Repository(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def backup_files(self):
        return sorted((self.db.parent / "backups").glob("*.sqlite3"))

    def test_new_backups_delete_entries_and_files_beyond_twelve(self):
        created = [self.repo.create_backup(f"Sicherung {index}") for index in range(15)]

        listed = self.repo.list_backups()
        listed_ids = {item["id"] for item in listed}
        self.assertEqual(BACKUP_RETENTION_LIMIT, len(listed))
        self.assertTrue({item["id"] for item in created[:3]}.isdisjoint(listed_ids))
        self.assertEqual(BACKUP_RETENTION_LIMIT, len(self.backup_files()))
        for item in created[:3]:
            self.assertFalse((self.db.parent / "backups" / item["file_name"]).exists())

        with self.repo.connect() as con:
            self.assertEqual(
                BACKUP_RETENTION_LIMIT,
                con.execute("SELECT COUNT(*) FROM app_backups").fetchone()[0],
            )

    def test_startup_prunes_an_existing_long_backup_history(self):
        created = [
            self.repo.create_backup(f"Altbestand {index}", prune=False)
            for index in range(15)
        ]
        self.assertEqual(15, len(self.backup_files()))

        reopened = Repository(self.db)

        self.assertEqual(BACKUP_RETENTION_LIMIT, len(reopened.list_backups()))
        self.assertEqual(BACKUP_RETENTION_LIMIT, len(self.backup_files()))
        for item in created[:3]:
            self.assertFalse((self.db.parent / "backups" / item["file_name"]).exists())

    def test_oldest_backup_can_be_restored_before_retention_runs(self):
        first_household = self.repo.create_household({
            "name": "Vorher",
            "mode": "single",
            "person_a": "Alex",
        })
        oldest = self.repo.create_backup("älteste Sicherung")
        self.repo.create_household({
            "name": "Soll verschwinden",
            "mode": "single",
            "person_a": "Bea",
        })
        for index in range(BACKUP_RETENTION_LIMIT - 1):
            self.repo.create_backup(f"Folgesicherung {index}")

        result = self.repo.restore_backup(oldest["id"])

        self.assertTrue(result["restored"])
        self.assertEqual(
            [first_household["id"]],
            [item["id"] for item in self.repo.list_households()],
        )
        listed = self.repo.list_backups()
        self.assertEqual(BACKUP_RETENTION_LIMIT, len(listed))
        self.assertIn(oldest["id"], {item["id"] for item in listed})
        self.assertEqual(BACKUP_RETENTION_LIMIT, len(self.backup_files()))


if __name__ == "__main__":
    unittest.main()
