import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace

from diagnostics import parse_text, write_report
from cae_adapter import create_diagnostic_set, prepare_selection

ROOT = Path(__file__).resolve().parents[1]


class ParserTests(unittest.TestCase):
    def test_repeated_labels_remain_instance_qualified(self):
        report = parse_text((ROOT / 'examples/distortion.msg').read_text())
        self.assertEqual(report['summary']['unique_elements'], 3)
        self.assertEqual(report['summary']['matched_occurrences'], 4)
        self.assertEqual(report['elements'][0]['source_lines'], [2, 3])
        self.assertEqual(report['unparsed_distortion_lines'][0]['line'], 7)

    def test_case_whitespace_and_crlf_wrapping(self):
        report = parse_text('element A-1.9\r\n is   distorting excessively\r\n'
                            'ELEMENT a-1.9 IS DISTORTING EXCESSIVELY')
        self.assertEqual(len(report['elements']), 1)
        self.assertEqual(report['elements'][0]['occurrences'], 2)
        self.assertEqual(report['unparsed_distortion_lines'], [])

    def test_unsupported_unqualified_element_is_reported(self):
        r = parse_text('ELEMENT 42 IS DISTORTING EXCESSIVELY')
        self.assertEqual(r['elements'], [])
        self.assertEqual(len(r['unparsed_distortion_lines']), 1)

    def test_empty_and_unrelated_error_do_not_imply_success(self):
        for text in ['', '***ERROR: unrelated failure']:
            r = parse_text(text)
            self.assertEqual(r['elements'], [])
            self.assertIn('Not a solver completion', r['summary']['interpretation'])

    def test_dotted_instance_names_and_same_line_occurrences(self):
        r = parse_text('ELEMENT ASSEMBLY.PART-1.12 IS DISTORTING EXCESSIVELY '
                       'ELEMENT ASSEMBLY.PART-1.13 IS DISTORTING EXCESSIVELY')
        self.assertEqual([(e['instance'], e['element_label']) for e in r['elements']],
                         [('ASSEMBLY.PART-1', 12), ('ASSEMBLY.PART-1', 13)])

    def test_reports_roundtrip_and_existing_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'report'
            r = parse_text('ELEMENT A-1.2 IS DISTORTING EXCESSIVELY')
            write_report(r, out)
            self.assertEqual(json.loads((out / 'report.json').read_text()), r)
            with (out / 'elements.csv').open(newline='') as f:
                self.assertEqual(list(csv.DictReader(f))[0]['element_label'], '2')
            with self.assertRaises(FileExistsError):
                write_report(r, out)
            self.assertEqual(json.loads((out / 'report.json').read_text()), r)

    def test_cli_exit_codes_and_no_source_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            for name, expected in [('distortion.msg', 2), ('no_supported_findings.msg', 0)]:
                out = Path(temp) / name
                result = subprocess.run([sys.executable, str(ROOT / 'diagnostics.py'),
                    str(ROOT / 'examples' / name), '--output', str(out),
                    '--fail-on-findings'], capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stderr)
            result = subprocess.run([sys.executable, str(ROOT / 'diagnostics.py'),
                str(ROOT / 'examples/distortion.msg'), '--output', str(out)],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)

    def test_decoding_error_leaves_no_report(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'bad.msg'
            source.write_bytes(b'\xff')
            out = Path(temp) / 'out'
            result = subprocess.run([sys.executable, str(ROOT / 'diagnostics.py'),
                str(source), '--output', str(out)], capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertFalse(out.exists())


class FakeAssembly:
    def __init__(self):
        self.instances = {name: SimpleNamespace(elements=[SimpleNamespace(label=label)])
                          for name, label in [('Bracket-1', 42), ('Plate-1', 42)]}
        self.sets = {}
        self.calls = []

    def SetFromElementLabels(self, **kwargs):
        self.calls.append(kwargs)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.assembly = FakeAssembly()
        self.report = parse_text('ELEMENT BRACKET-1.42 IS DISTORTING EXCESSIVELY\n'
                                 'ELEMENT PLATE-1.42 IS DISTORTING EXCESSIVELY')

    def test_preview_keeps_instances_and_does_not_mutate(self):
        selection = create_diagnostic_set(self.assembly, self.report)
        self.assertEqual(selection, (('Bracket-1', (42,)), ('Plate-1', (42,))))
        self.assertEqual(self.assembly.calls, [])

    def test_explicit_apply_creates_one_assembly_set(self):
        create_diagnostic_set(self.assembly, self.report, apply=True)
        self.assertEqual(len(self.assembly.calls), 1)
        self.assertEqual(len(self.assembly.calls[0]['elementLabels']), 2)

    def test_missing_instance_or_label_rejects_before_mutation(self):
        for text in ['ELEMENT LOST-1.42 IS DISTORTING EXCESSIVELY',
                     'ELEMENT BRACKET-1.99 IS DISTORTING EXCESSIVELY']:
            with self.assertRaises(ValueError):
                create_diagnostic_set(self.assembly, parse_text(text), apply=True)
        self.assertEqual(self.assembly.calls, [])

    def test_collision_empty_and_bad_identity_reject(self):
        self.assembly.sets['DIAGNOSTIC_DISTORTED'] = object()
        with self.assertRaises(ValueError):
            create_diagnostic_set(self.assembly, self.report, apply=True)
        with self.assertRaises(ValueError):
            create_diagnostic_set(self.assembly, parse_text(''), name='EMPTY')
        self.report['elements'][0]['element_label'] = True
        with self.assertRaises(ValueError):
            prepare_selection(self.assembly, self.report)
        self.assertEqual(self.assembly.calls, [])


if __name__ == '__main__':
    unittest.main()
