import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class OfflineSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.tmpdir.name) / "test_offline.db"
        os.environ["OFFLINE_MODE"] = "1"
        os.environ["OFFLINE_DB_PATH"] = str(cls.db_path)

        # Imports após setar env
        global db, ingest, search
        import database as db  # type: ignore
        import ingest as ingest  # type: ignore
        import search as search  # type: ignore

        cls.db = db
        cls.ingest = ingest
        cls.search = search

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def test_01_sqlite_mode_enabled(self):
        self.assertTrue(self.db.IS_SQLITE)

    def test_02_ingest_pdf_and_query(self):
        pdf = Path("executivo/PoderExecutivo20260520.pdf")
        self.assertTrue(pdf.exists(), f"PDF não encontrado: {pdf}")

        self.ingest.ingest(pdf)

        rows = self.search.fulltext_search("educação crédito", limit=3)
        self.assertGreater(len(rows), 0)

    def test_03_stats_tables_have_rows(self):
        with self.db.get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM publicacoes")
            pub_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM atos")
            atos_count = cur.fetchone()[0]
            cur.close()

        self.assertGreaterEqual(pub_count, 1)
        self.assertGreaterEqual(atos_count, 1)


if __name__ == "__main__":
    unittest.main()
