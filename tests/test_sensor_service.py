"""Observable review, evidence, and retraction behavior for sensor batches."""
import unittest
from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

from agent.database import db
from agent.sensors.adapters import HealthConnectAdapter, PixelAdapter
from agent.sensors.repository import SensorBatchChanged, SensorRepository
from agent.sensors.service import SensorService


class SensorServiceTests(unittest.TestCase):
    def setUp(self):
        self.user_id = db.create_user(f"sensor_owner_{uuid4().hex}")
        self.other_user_id = db.create_user(f"sensor_other_{uuid4().hex}")
        self.theme_ids = []
        self.batch_ids = []
        self.service = SensorService()
        self.repository = SensorRepository()

    def tearDown(self):
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM pattern_confidence WHERE pattern_type = 'theme' "
                        "AND pattern_id = ANY(%s)", (self.theme_ids,))
            cur.execute("DELETE FROM themes WHERE id = ANY(%s)", (self.theme_ids,))
            cur.execute("DELETE FROM sensor_batches WHERE id = ANY(%s)", (self.batch_ids,))
            cur.execute("DELETE FROM users WHERE id = ANY(%s)",
                        ([self.user_id, self.other_user_id],))
            conn.commit()

    def theme(self, user_id=None, status="active"):
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO themes (user_id, summary, claim_kind,
                           centroid_embedding, first_seen_at, last_seen_at, status)
                   VALUES (%s, 'Sensor theme', 'mention',
                           (SELECT array_fill(0, ARRAY[1536])::vector), now(), now(), %s)
                   RETURNING id""", (user_id if user_id is not None else self.user_id, status))
            theme_id = cur.fetchone()[0]
            conn.commit()
            self.theme_ids.append(theme_id)
            return theme_id

    def stage(self, observations, **extra):
        batch_id = self.service.stage_delivery(
            {"source": "pixel", "observations": observations, **extra},
            delivery_key=uuid4().hex,
            review_day=date(2026, 1, 1) + timedelta(days=len(self.batch_ids)),
            clock_skew_seconds=None,
        )
        self.batch_ids.append(batch_id)
        return batch_id

    @staticmethod
    def reading(hash_, timestamp, source_type="pixel_steps", value=1200):
        return {"source_type": source_type, "occurred_at": timestamp,
                "value_num": value, "payload_hash": hash_}

    def test_commit_stores_unlinked_raw_readings_but_counts_only_approved_links(self):
        theme_id = self.theme()
        batch_id = self.stage([
            self.reading("steps", "2026-09-22"),
            self.reading("app", "2026-09-22T10:05:00Z", "pixel_app_usage"),
        ])
        ids = self.service.commit_batch(batch_id, links={
            "pixel_steps": theme_id, "pixel_app_usage": None}, user_id=self.user_id)

        self.assertEqual(len(ids), 2)
        batch = self.repository.get_batch(batch_id)
        self.assertEqual(batch["status"], "confirmed")
        self.assertEqual(batch["theme_links"], {"pixel_steps": theme_id})
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT source_type, occurred_date, occurred_at "
                        "FROM sensor_observations WHERE batch_id = %s ORDER BY id", (batch_id,))
            rows = cur.fetchall()
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0][1].isoformat(), "2026-09-22")
            self.assertEqual(rows[0][2], datetime(2026, 9, 22, tzinfo=UTC))
            cur.execute("SELECT source_type, snippet FROM theme_occurrences "
                        "WHERE theme_id = %s", (theme_id,))
            self.assertEqual(cur.fetchall(), [("pixel_steps", "1200 steps")])
            cur.execute("SELECT occurrence_count FROM themes WHERE id = %s", (theme_id,))
            self.assertEqual(cur.fetchone()[0], 1)

    def test_cap_respects_constant_and_utc_days_across_batches(self):
        theme_id = self.theme()
        # Patch to 2: a hard-coded 'one per day' would fail this boundary.
        with patch("agent.sensors.repository.MAX_SENSOR_OCCURRENCES_PER_DAY_PER_THEME", 2):
            first = self.stage([
                self.reading("first", "2026-09-22T23:30:00-02:00", value=100),
                self.reading("second", "2026-09-23T08:00:00Z", value=200),
            ])
            self.service.commit_batch(first, links={"pixel_steps": theme_id}, user_id=self.user_id)
            second = self.stage([
                self.reading("third", "2026-09-23T12:00:00Z", value=300),
                self.reading("fourth", "2026-09-24"),
            ])
            self.service.commit_batch(second, links={"pixel_steps": theme_id}, user_id=self.user_id)
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT (occurred_at AT TIME ZONE 'UTC')::date, count(*) "
                        "FROM theme_occurrences WHERE theme_id = %s GROUP BY 1 ORDER BY 1",
                        (theme_id,))
            self.assertEqual([(str(day), count) for day, count in cur.fetchall()],
                             [("2026-09-23", 2), ("2026-09-24", 1)])
            cur.execute(
                """SELECT snippet FROM theme_occurrences
                   WHERE theme_id = %s AND source_type = 'pixel_steps'
                     AND (occurred_at AT TIME ZONE 'UTC')::date = '2026-09-23'""",
                (theme_id,))
            self.assertEqual({row[0] for row in cur.fetchall()}, {"200 steps", "300 steps"})
            cur.execute("SELECT count(*) FROM sensor_observations WHERE batch_id = %s",
                        (second,))
            self.assertEqual(cur.fetchone()[0], 2)

    def test_live_retry_and_rolling_daily_steps_restore_previous_confirmed_snapshot(self):
        theme_id = self.theme()
        def snapshot(count):
            return PixelAdapter().parse_from_dict({
                "device": "Pixel 10a",
                "exported_at": "2026-09-23T12:00:00Z",
                "tiers": {"steps": [{"date": "2026-09-23", "count": count}]},
            })

        first_payload = snapshot(1200)
        first_key = "a" * 64
        first = self.service.stage_delivery(
            first_payload, delivery_key=first_key,
            review_day=date(2026, 9, 23), clock_skew_seconds=None)
        self.batch_ids.append(first)
        self.assertEqual(self.service.stage_delivery(
            first_payload, delivery_key=first_key,
            review_day=date(2026, 9, 23), clock_skew_seconds=None), first)
        self.service.commit_batch(first, links={"pixel_steps": theme_id}, user_id=self.user_id)
        self.assertEqual(self.service.stage_delivery(
            first_payload, delivery_key=first_key,
            review_day=date(2026, 9, 23), clock_skew_seconds=None), first)

        later_payload = snapshot(4500)
        later_key = "b" * 64
        later = self.service.stage_delivery(
            later_payload, delivery_key=later_key,
            review_day=date(2026, 9, 23), clock_skew_seconds=None)
        self.batch_ids.append(later)
        self.service.commit_batch(later, links={"pixel_steps": theme_id}, user_id=self.user_id)

        def evidence():
            with db.connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """SELECT t.source_id, t.snippet, s.value_num
                       FROM theme_occurrences t
                       JOIN sensor_observations s
                         ON s.id = t.source_id AND s.source_type = t.source_type
                       WHERE t.theme_id = %s AND t.source_type = 'pixel_steps'""",
                    (theme_id,))
                rows = cur.fetchall()
                cur.execute("SELECT occurrence_count FROM themes WHERE id = %s", (theme_id,))
                count = cur.fetchone()[0]
                cur.execute("SELECT count(*) FROM sensor_batches WHERE id = ANY(%s)",
                            ([first, later],))
                batches = cur.fetchone()[0]
                return rows, count, batches

        rows, count, batches = evidence()
        self.assertEqual([(snippet, value) for _, snippet, value in rows],
                         [("4500 steps", 4500.0)])
        self.assertEqual((count, batches), (1, 2))
        self.repository.delete_batch(later)
        rows, count, batches = evidence()
        self.assertEqual([(snippet, value) for _, snippet, value in rows],
                         [("1200 steps", 1200.0)])
        self.assertEqual((count, batches), (1, 1))
        self.repository.delete_batch(first)
        self.assertEqual(evidence(), ([], 0, 0))

    def test_late_confirmation_of_older_daily_snapshot_does_not_replace_newer_total(self):
        theme_id = self.theme()
        older = self.stage([self.reading("early", "2026-09-23", value=1200)])
        newer = self.stage([self.reading("later", "2026-09-23", value=4500)])
        self.service.commit_batch(newer, links={"pixel_steps": theme_id}, user_id=self.user_id)
        self.service.commit_batch(older, links={"pixel_steps": theme_id}, user_id=self.user_id)

        def daily_evidence():
            with db.connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """SELECT t.snippet, s.batch_id
                       FROM theme_occurrences t
                       JOIN sensor_observations s
                         ON s.id = t.source_id AND s.source_type = t.source_type
                       WHERE t.theme_id = %s AND t.source_type = 'pixel_steps'""",
                    (theme_id,))
                rows = cur.fetchall()
                cur.execute("SELECT occurrence_count FROM themes WHERE id = %s", (theme_id,))
                return rows, cur.fetchone()[0]

        self.assertEqual(daily_evidence(), ([("4500 steps", newer)], 1))
        self.repository.delete_batch(newer)
        self.assertEqual(daily_evidence(), ([("1200 steps", older)], 1))

    def test_invalid_source_and_foreign_or_inactive_theme_leave_batch_pending(self):
        foreign_theme = self.theme(user_id=self.other_user_id)
        inactive_theme = self.theme(status="rejected")
        batch_id = self.stage([self.reading("valid", "2026-09-22")])
        for links in ({"not_in_batch": foreign_theme},
                      {"pixel_steps": foreign_theme},
                      {"pixel_steps": inactive_theme}):
            with self.subTest(links=links), self.assertRaises(ValueError):
                self.service.commit_batch(batch_id, links=links, user_id=self.user_id)
            with db.connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT status, theme_links FROM sensor_batches WHERE id = %s",
                            (batch_id,))
                self.assertEqual(cur.fetchone(), ("pending", None))
                cur.execute("SELECT count(*) FROM sensor_observations WHERE batch_id = %s",
                            (batch_id,))
                self.assertEqual(cur.fetchone()[0], 0)
        own_theme = self.theme()
        self.assertEqual(len(self.service.commit_batch(
            batch_id, links={"pixel_steps": own_theme}, user_id=self.user_id)), 1)

    def test_idempotent_same_links_but_not_changed_links_or_rejected_batch(self):
        theme_id = self.theme()
        batch_id = self.stage([self.reading("one", "2026-09-22")])
        ids = self.service.commit_batch(batch_id, links={"pixel_steps": theme_id}, user_id=self.user_id)
        self.assertEqual(self.service.commit_batch(
            batch_id, links={"pixel_steps": theme_id}, user_id=self.user_id), ids)
        with self.assertRaises(ValueError):
            self.service.commit_batch(batch_id, links={}, user_id=self.user_id)
        with self.assertRaises(ValueError):
            self.repository.reject_batch(batch_id)
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM theme_occurrences WHERE theme_id = %s", (theme_id,))
            self.assertEqual(cur.fetchone()[0], 1)
        rejected_id = self.stage([])
        self.repository.reject_batch(rejected_id)
        with self.assertRaises(ValueError):
            self.service.commit_batch(rejected_id, links={}, user_id=self.user_id)

    def test_delete_confirmed_retracts_counts_and_invalidates_cached_analysis(self):
        theme_id = self.theme()
        first = self.stage([self.reading("first", "2026-09-22")])
        second = self.stage([self.reading("second", "2026-09-23")])
        self.service.commit_batch(first, links={"pixel_steps": theme_id}, user_id=self.user_id)
        self.service.commit_batch(second, links={"pixel_steps": theme_id}, user_id=self.user_id)
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO pattern_confidence (pattern_type, pattern_id) "
                        "VALUES ('theme', %s)", (theme_id,))
            conn.commit()
        self.repository.delete_batch(first)
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT occurrence_count FROM themes WHERE id = %s", (theme_id,))
            self.assertEqual(cur.fetchone()[0], 1)
            cur.execute("SELECT count(*) FROM theme_occurrences WHERE theme_id = %s", (theme_id,))
            self.assertEqual(cur.fetchone()[0], 1)
            cur.execute("SELECT last_computed_at FROM pattern_confidence "
                        "WHERE pattern_type = 'theme' AND pattern_id = %s", (theme_id,))
            self.assertIsNone(cur.fetchone()[0])
        self.repository.delete_batch(second)
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT occurrence_count FROM themes WHERE id = %s", (theme_id,))
            self.assertEqual(cur.fetchone()[0], 0)

    def test_stage_persists_dropped_readings_and_device_clock_and_reported_skew(self):
        batch = PixelAdapter().parse_from_dict({
            "device": "Pixel 10a", "exported_at": "2026-09-22T18:00:00Z",
            "tiers": {"steps": [{"date": "2026-09-22", "count": 100},
                                  {"date": None, "count": 200}]}})
        batch_id = self.service.stage_delivery(
            batch, delivery_key=uuid4().hex,
            review_day=date(2026, 9, 22), clock_skew_seconds=12)
        self.batch_ids.append(batch_id)
        detail = self.repository.get_batch(batch_id)
        listing = next(row for row in self.repository.list_batches() if row["id"] == batch_id)
        self.assertEqual(detail["dropped_count"], 1)
        self.assertEqual(detail["observation_count"], 1)
        self.assertNotIn("parsed_payload", listing)
        self.assertEqual(listing["observation_count"], detail["observation_count"])
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT device_clock, clock_skew_seconds "
                        "FROM sensor_batches WHERE id = %s", (batch_id,))
            device, skew = cur.fetchone()
        self.assertEqual(device, datetime(2026, 9, 22, 18, tzinfo=UTC))
        self.assertEqual(skew, 12)

    def test_deliveries_merge_into_one_pending_batch_per_source_and_day(self):
        day = date(2026, 9, 23)
        def pixel(count):
            return {"source": "pixel", "observations": [
                self.reading(f"steps-{count}", "2026-09-23", value=count)]}
        first = self.service.stage_delivery(
            pixel(1200), delivery_key="c" * 64, review_day=day, clock_skew_seconds=None)
        self.batch_ids.append(first)
        later = self.service.stage_delivery(
            pixel(4500), delivery_key="d" * 64, review_day=day, clock_skew_seconds=None)
        self.assertEqual(first, later)
        detail = self.repository.get_batch(first)
        self.assertEqual(detail["observation_count"], 2)
        self.assertEqual([o["value_num"] for o in detail["parsed_payload"]["observations"]],
                         [1200, 4500])
        self.assertEqual(self.service.stage_delivery(
            pixel(1200), delivery_key="c" * 64, review_day=day,
            clock_skew_seconds=None), first)
        self.assertEqual(self.repository.get_batch(first)["observation_count"], 2)
        health_connect = self.service.stage_delivery(
            {"source": "health_connect", "observations": []},
            delivery_key="e" * 64, review_day=day, clock_skew_seconds=None)
        self.batch_ids.append(health_connect)
        self.assertNotEqual(first, health_connect)
        self.service.commit_batch(first, links={}, user_id=self.user_id)
        next_batch = self.service.stage_delivery(
            pixel(9000), delivery_key="f" * 64, review_day=day, clock_skew_seconds=None)
        self.batch_ids.append(next_batch)
        self.assertNotEqual(first, next_batch)

    def test_confirm_refuses_batch_that_grew_after_review(self):
        day = date(2026, 9, 23)
        first = self.service.stage_delivery(
            {"source": "pixel", "observations": [self.reading("first", "2026-09-23")]},
            delivery_key="g" * 64, review_day=day, clock_skew_seconds=None)
        self.batch_ids.append(first)
        self.service.stage_delivery(
            {"source": "pixel", "observations": [self.reading("second", "2026-09-23")]},
            delivery_key="h" * 64, review_day=day, clock_skew_seconds=None)
        with self.assertRaises(SensorBatchChanged):
            self.service.commit_batch(first, links={}, user_id=self.user_id,
                                      expected_observation_count=1)
        self.assertEqual(self.repository.get_batch(first)["status"], "pending")
        self.service.commit_batch(first, links={}, user_id=self.user_id,
                                  expected_observation_count=2)
        self.assertEqual(self.repository.get_batch(first)["status"], "confirmed")


    def test_old_pending_batch_without_parsed_payload_cannot_be_confirmed(self):
        batch_id = self.stage([])
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("UPDATE sensor_batches SET parsed_payload = NULL WHERE id = %s",
                        (batch_id,))
            conn.commit()
        with self.assertRaisesRegex(ValueError, "no parsed observations"):
            self.service.commit_batch(batch_id, links={}, user_id=self.user_id)
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT status, confirmed_at FROM sensor_batches WHERE id = %s",
                        (batch_id,))
            self.assertEqual(cur.fetchone(), ("pending", None))

    def test_adapters_drop_missing_measurements_without_dropping_real_zero(self):
        pixel = PixelAdapter().parse_from_dict({
            "device": "Pixel 10a",
            "tiers": {
                "steps": [{"date": "2026-09-22"}, {"date": "2026-09-23", "count": 0}],
                "location": [{"ts": "2026-09-22T10:00:00Z", "lat": 0}],
                "app_usage": [{"ts": "2026-09-22T11:00:00Z",
                               "foreground_seconds": 12}],
            },
        })
        self.assertEqual(pixel["dropped_count"], 3)
        self.assertEqual([obs["value_num"] for obs in pixel["observations"]], [0])
        health_connect = HealthConnectAdapter().parse_from_dict({
            "device": "Health Connect",
            "tiers": {
                "heart_rate": [{"ts": "2026-09-22T10:00:00Z", "context": "resting"}],
                "sleep": [{"date": "2026-09-22", "stage_summary": "deep"}],
                "spo2": [{"ts": "2026-09-22T11:00:00Z"}],
            },
        })
        self.assertEqual(health_connect["observations"], [])
        self.assertEqual(health_connect["dropped_count"], 3)

    def test_incomplete_manually_staged_reading_cannot_become_evidence(self):
        theme_id = self.theme()
        batch_id = self.stage([
            {"source_type": "pixel_steps", "occurred_at": "2026-09-22",
             "payload_hash": "missing_value"},
            self.reading("valid_value", "2026-09-23"),
        ])
        with self.assertRaisesRegex(ValueError, "no essential measurement"):
            self.service.commit_batch(batch_id, links={"pixel_steps": theme_id},
                                      user_id=self.user_id)
        self.assertEqual(self.repository.get_batch(batch_id)["status"], "pending")
        # Keeping the incomplete raw sample is allowed when no link admits it.
        self.assertEqual(len(self.service.commit_batch(
            batch_id, links={}, user_id=self.user_id)), 2)
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM theme_occurrences WHERE theme_id = %s",
                        (theme_id,))
            self.assertEqual(cur.fetchone()[0], 0)

    def test_unknown_batch_is_an_error_for_all_mutations(self):
        with self.assertRaises(ValueError):
            self.service.commit_batch(-1, links={}, user_id=self.user_id)
        with self.assertRaises(ValueError):
            self.repository.reject_batch(-1)
        with self.assertRaises(ValueError):
            self.repository.delete_batch(-1)
