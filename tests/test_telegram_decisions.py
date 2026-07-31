import tempfile
import unittest
from pathlib import Path

from ops.telegram_decisions import (
    BridgeConfig,
    DecisionStore,
    TelegramCredentials,
    deliver_one,
    process_update,
    selection_prompt,
    validate_question,
)


THREAD_ID = "019fb812-daa4-70b0-a261-04f2a41c9e53"


class FakeAppServer:
    status = "idle"
    turn_starts = []

    def __init__(self, _socket_path):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def thread_read(self, thread_id):
        return {
            "id": thread_id,
            "status": {"type": self.status},
            "canAcceptDirectInput": True,
        }

    def thread_resume(self, thread_id, _cwd):
        return {
            "id": thread_id,
            "status": {"type": "idle"},
            "canAcceptDirectInput": True,
        }

    def turn_start(self, thread_id, cwd, text, client_message_id):
        self.turn_starts.append((thread_id, cwd, text, client_message_id))
        return {"id": "turn-1", "status": "inProgress", "items": []}


class TelegramDecisionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = DecisionStore(self.root / "state.sqlite3")
        self.config = BridgeConfig(
            thread_id=THREAD_ID,
            cwd=self.root,
            allowed_user_id=1234,
            app_server_socket=self.root / "socket",
            state_db=self.root / "state.sqlite3",
            telegram_config=self.root / "telegram.json",
        )
        self.credentials = TelegramCredentials("test-token", "1234")
        FakeAppServer.turn_starts = []
        FakeAppServer.status = "idle"

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def register(self, now=1000, ttl=600):
        decision_id, tokens = self.store.create_decision(
            "Which path?", ["Cloud", "Mobile"], THREAD_ID, self.root, now, ttl
        )
        self.store.mark_sent(decision_id, 99)
        return decision_id, tokens

    def update(self, update_id, token, user_id=1234, chat_id=1234):
        return {
            "update_id": update_id,
            "callback_query": {
                "id": f"callback-{update_id}",
                "from": {"id": user_id},
                "data": f"armd:{token}",
                "message": {
                    "message_id": 99,
                    "chat": {"id": chat_id, "type": "private"},
                },
            },
        }

    def test_registered_callback_dispatches_exact_option_once(self):
        _decision_id, tokens = self.register()
        outcome, callback_id, message_id = process_update(
            self.store,
            self.config,
            self.credentials,
            self.update(7, tokens[1]),
            1100,
        )
        self.assertEqual("selected", outcome.status)
        self.assertEqual("Mobile", outcome.selection.option_label)
        self.assertEqual("callback-7", callback_id)
        self.assertEqual(99, message_id)
        prompt = selection_prompt(outcome.selection)
        self.assertIn("Selected option 2: Mobile", prompt)
        self.assertEqual(
            "dispatched",
            deliver_one(
                self.store, self.config, client_factory=FakeAppServer, now=1101
            ),
        )
        self.assertEqual(1, len(FakeAppServer.turn_starts))
        self.assertEqual(THREAD_ID, FakeAppServer.turn_starts[0][0])
        duplicate, _, _ = process_update(
            self.store,
            self.config,
            self.credentials,
            self.update(7, tokens[1]),
            1102,
        )
        self.assertEqual("duplicate", duplicate.status)

    def test_unauthorized_callback_cannot_select(self):
        _decision_id, tokens = self.register()
        outcome, _, _ = process_update(
            self.store,
            self.config,
            self.credentials,
            self.update(8, tokens[0], user_id=9999),
            1100,
        )
        self.assertEqual("unauthorized", outcome.status)
        self.assertIsNone(self.store.next_queued())

    def test_expired_callback_cannot_select(self):
        _decision_id, tokens = self.register(ttl=10)
        outcome, _, _ = process_update(
            self.store,
            self.config,
            self.credentials,
            self.update(9, tokens[0]),
            1011,
        )
        self.assertEqual("expired", outcome.status)
        self.assertIsNone(self.store.next_queued())

    def test_active_thread_keeps_decision_queued(self):
        _decision_id, tokens = self.register()
        process_update(
            self.store,
            self.config,
            self.credentials,
            self.update(10, tokens[0]),
            1100,
        )
        FakeAppServer.status = "active"
        self.assertEqual(
            "busy",
            deliver_one(
                self.store, self.config, client_factory=FakeAppServer, now=1101
            ),
        )
        self.assertIsNotNone(self.store.next_queued())
        self.assertEqual([], FakeAppServer.turn_starts)

    def test_question_validation_rejects_free_form_shape(self):
        with self.assertRaisesRegex(Exception, "two or three"):
            validate_question("Choose", ["Only one"])
        question, options = validate_question(
            "  Choose   a track ", [" Cloud ", " Mobile "]
        )
        self.assertEqual("Choose a track", question)
        self.assertEqual(["Cloud", "Mobile"], options)


if __name__ == "__main__":
    unittest.main()
