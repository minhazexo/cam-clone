"""Unit tests for the job layer: events vocabulary, JobStore transitions, SSE."""

import json
import unittest

from rscan.errors import JobNotFoundError
from rscan.jobs import events
from rscan.jobs.job_store import JobStore, drain
from rscan.services.scan_progress_service import format_frame, stream_job_events


class EventsTest(unittest.TestCase):
    def test_payload_shapes(self):
        self.assertEqual(events.loading(), {"type": "loading"})
        self.assertEqual(events.detected(7), {"type": "detected", "total": 7})
        self.assertEqual(events.scanning(2, 7), {"type": "scanning", "page": 2, "total": 7})
        self.assertEqual(events.page_done(2, 7), {"type": "page_done", "page": 2, "total": 7})
        self.assertEqual(events.assembling(), {"type": "assembling"})
        self.assertEqual(events.done("scanned_a.pdf", 1.5),
                         {"type": "done", "pdf": "scanned_a.pdf", "elapsed": 1.5})
        self.assertEqual(events.error("bad"), {"type": "error", "message": "bad"})
        self.assertEqual(events.eof(), {"type": "_eof"})

    def test_terminal_events(self):
        for event in (events.done("x.pdf", 1), events.error("x"), events.eof()):
            self.assertTrue(events.is_terminal(event))
        for event in (events.loading(), events.detected(1), events.scanning(1, 1),
                      events.page_done(1, 1), events.assembling()):
            self.assertFalse(events.is_terminal(event))


class JobStoreTest(unittest.TestCase):
    def setUp(self):
        self.store = JobStore(ttl_seconds=600)

    def test_create_get_push(self):
        job = self.store.create()
        self.assertTrue(job.id)
        self.assertIs(self.store.get(job.id), job)
        self.store.push(job.id, events.loading())
        self.assertEqual(drain(job), [{"type": "loading"}])

    def test_unknown_job_lookup_and_push_are_safe(self):
        self.assertIsNone(self.store.get("nope"))
        self.store.push("nope", events.loading())  # must not raise

    def test_job_ids_are_unique(self):
        ids = {self.store.create().id for _ in range(50)}
        self.assertEqual(len(ids), 50)

    def test_delete_removes_the_job(self):
        job = self.store.create()
        self.store.delete(job.id)
        self.assertIsNone(self.store.get(job.id))

    def test_cleanup_removes_only_expired_jobs(self):
        store = JobStore(ttl_seconds=0.05)
        old = store.create()
        store.create()
        # Age one job beyond the TTL by rewinding its creation timestamp.
        store.get(old.id).created_at -= 10
        removed = store.cleanup()
        self.assertEqual(removed, 1)
        self.assertIsNone(store.get(old.id))
        self.assertEqual(len(store), 1)

    def test_full_lifecycle_matches_the_documented_event_order(self):
        job = self.store.create()
        for event in (events.loading(), events.detected(2), events.scanning(1, 2),
                      events.page_done(1, 2), events.page_done(2, 2),
                      events.assembling(), events.done("scanned_x.pdf", 2.0),
                      events.eof()):
            self.store.push(job.id, event)
        types = [event["type"] for event in drain(job)]
        self.assertEqual(types, ["loading", "detected", "scanning", "page_done",
                                 "page_done", "assembling", "done", "_eof"])


class ProgressStreamTest(unittest.TestCase):
    def test_frames_are_sse_data_lines(self):
        self.assertEqual(format_frame('{"type":"loading"}'), 'data: {"type":"loading"}\n\n')

    def test_stream_stops_at_terminal_events(self):
        store = JobStore()
        job = store.create()
        store.push(job.id, events.loading())
        store.push(job.id, events.done("scanned_x.pdf", 1.0))
        store.push(job.id, events.eof())  # never reached by the client

        frames = list(stream_job_events(job, keepalive_seconds=1))
        payloads = [json.loads(frame[len("data: "):]) for frame in frames]
        self.assertEqual([p["type"] for p in payloads], ["loading", "done"])

    def test_unknown_job_id_raises(self):
        from rscan.services.scan_progress_service import stream_job

        with self.assertRaises(JobNotFoundError):
            stream_job("missing", JobStore())


if __name__ == "__main__":
    unittest.main()
