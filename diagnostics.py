"""Report a bounded set of Abaqus excessive-distortion messages (Python 3.9+)."""
import argparse
from bisect import bisect_right
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

ELEMENT = re.compile(
    r"\bELEMENT\s+(?P<instance>[A-Z_][A-Z0-9_.:\-]*)\."
    r"(?P<label>[1-9][0-9]*)\s+IS\s+DISTORTING\s+EXCESSIVELY\b",
    re.IGNORECASE,
)
POSSIBLE = re.compile(r"DISTORT\w*.*EXCESS\w*|EXCESS\w*.*DISTORT\w*", re.I)


def parse_text(text):
    """Keep instance identity, repeated occurrences and original 1-based lines."""
    starts = [0] + [m.end() for m in re.finditer(r"\n", text)]
    grouped, covered = {}, set()
    for match in ELEMENT.finditer(text):
        first = bisect_right(starts, match.start())
        last = bisect_right(starts, match.end() - 1)
        covered.update(range(first, last + 1))
        key = (match['instance'].upper(), int(match['label']))
        item = grouped.setdefault(key, {
            'instance': key[0], 'element_label': key[1],
            'occurrences': 0, 'source_lines': [],
        })
        item['occurrences'] += 1
        item['source_lines'].append(first)
    unparsed = [
        {'line': i, 'text': line.strip()}
        for i, line in enumerate(text.splitlines(), 1)
        if i not in covered and POSSIBLE.search(line)
    ]
    return {
        'schema_version': 1,
        'scope': 'instance-qualified excessive element distortion messages only',
        'elements': [grouped[key] for key in sorted(grouped)],
        'unparsed_distortion_lines': unparsed,
        'summary': {
            'unique_elements': len(grouped),
            'matched_occurrences': sum(v['occurrences'] for v in grouped.values()),
            'unparsed_distortion_lines': len(unparsed),
            'interpretation': 'Not a solver completion or model-validity assessment.',
        },
    }


def write_report(report, output):
    """Require a new directory; do not overwrite an earlier report."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    with (output / 'report.json').open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
    with (output / 'elements.csv').open('x', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['instance', 'element_label', 'occurrences', 'source_lines'])
        for item in report['elements']:
            writer.writerow([item['instance'], item['element_label'],
                             item['occurrences'], ';'.join(map(str, item['source_lines']))])
    with (output / 'unparsed.csv').open('x', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['line', 'text'])
        for item in report['unparsed_distortion_lines']:
            writer.writerow([item['line'], item['text']])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('message_file', type=Path)
    parser.add_argument('--output', type=Path, required=True,
                        help='new report directory; existing directories are rejected')
    parser.add_argument('--encoding', default='utf-8-sig')
    parser.add_argument('--fail-on-findings', action='store_true',
                        help='exit 2 if matched elements or unparsed distortion lines exist')
    args = parser.parse_args(argv)
    try:
        raw = args.message_file.read_bytes()
        text = raw.decode(args.encoding)
        report = parse_text(text)
        report['source'] = {'filename': args.message_file.name,
                            'sha256': hashlib.sha256(raw).hexdigest(),
                            'encoding': args.encoding}
        write_report(report, args.output)
    except (OSError, UnicodeError, LookupError, ValueError) as exc:
        print('Error: {}'.format(exc), file=sys.stderr)
        return 1
    summary = report['summary']
    print('Unique elements: {}; occurrences: {}; unparsed distortion lines: {}'.format(
        summary['unique_elements'], summary['matched_occurrences'],
        summary['unparsed_distortion_lines']))
    print('Report: {}'.format(args.output))
    print(summary['interpretation'])
    findings = bool(report['elements'] or report['unparsed_distortion_lines'])
    return 2 if args.fail_on_findings and findings else 0


if __name__ == '__main__':
    sys.exit(main())
