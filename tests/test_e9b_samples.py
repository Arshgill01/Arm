import hashlib
import json
import unittest

from experiments.e9b_samples import SAMPLES_PER_TASK, TASK_SPLIT_SIZES, sample_map
from experiments.e9b_tasks.e9b_utils import winogrande_choices, winogrande_target


class E9bSamplesTests(unittest.TestCase):
    def test_sample_map_is_stable_and_in_range(self) -> None:
        samples = sample_map()
        self.assertEqual(set(samples), set(TASK_SPLIT_SIZES))
        for task, values in samples.items():
            self.assertEqual(len(values), SAMPLES_PER_TASK)
            self.assertEqual(values, sorted(set(values)))
            self.assertGreaterEqual(values[0], 0)
            self.assertLess(values[-1], TASK_SPLIT_SIZES[task])

    def test_sample_map_hash_is_frozen(self) -> None:
        encoded = json.dumps(sample_map(), indent=2, sort_keys=True) + "\n"
        self.assertEqual(
            hashlib.sha256(encoded.encode()).hexdigest(),
            "c92200f74c83666ee9e381e5edcb5d10bc66d8051ec07e9daa6805eab7632e49",
        )

    def test_winogrande_transform_matches_partial_evaluation(self) -> None:
        doc = {
            "sentence": "The trophy doesn't fit because _ is too large.",
            "option1": "the trophy",
            "option2": "the suitcase",
            "answer": "1",
        }
        self.assertEqual(winogrande_target(doc), "is too large.")
        self.assertEqual(
            winogrande_choices(doc),
            [
                "The trophy doesn't fit because the trophy",
                "The trophy doesn't fit because the suitcase",
            ],
        )


if __name__ == "__main__":
    unittest.main()
