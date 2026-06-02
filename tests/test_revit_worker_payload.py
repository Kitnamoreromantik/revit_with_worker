import unittest

from run_revit_worker import RevitCodeGeneratorWorker


class RevitWorkerPayloadTest(unittest.TestCase):
    def test_extracts_question_from_params_question(self):
        question = RevitCodeGeneratorWorker._extract_question(
            {"params": {"question": "  Create a wall  "}}
        )

        self.assertEqual(question, "Create a wall")

    def test_extracts_question_from_top_level_prompt(self):
        question = RevitCodeGeneratorWorker._extract_question(
            {"prompt": "  Сколько труб?  "}
        )

        self.assertEqual(question, "Сколько труб?")

    def test_extracts_question_from_params_prompt_literal_string(self):
        question = RevitCodeGeneratorWorker._extract_question(
            {"params": "{'prompt': '  Сколько труб?  '}"}
        )

        self.assertEqual(question, "Сколько труб?")

    def test_extracts_question_from_params_question_json_string(self):
        question = RevitCodeGeneratorWorker._extract_question(
            {"params": '{"question": "  Count pipes  "}'}
        )

        self.assertEqual(question, "Count pipes")

    def test_extracts_question_from_top_level_question(self):
        question = RevitCodeGeneratorWorker._extract_question(
            {"question": "  Count windows  "}
        )

        self.assertEqual(question, "Count windows")

    def test_rejects_payload_without_question_or_prompt(self):
        with self.assertRaisesRegex(ValueError, "params.question.*top-level 'prompt'"):
            RevitCodeGeneratorWorker._extract_question({"params": {}})
