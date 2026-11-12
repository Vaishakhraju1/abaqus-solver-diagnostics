"""Optional CAE adapter. No Abaqus imports and no model changes on import."""
import re


def prepare_selection(assembly, report):
    """Validate every identity before returning SetFromElementLabels arguments."""
    if report.get('schema_version') != 1:
        raise ValueError('Unsupported report schema')
    if not isinstance(report.get('elements'), list):
        raise ValueError('Report elements must be a list')
    by_case = {}
    for name in assembly.instances.keys():
        by_case.setdefault(name.upper(), []).append(name)
    grouped, seen = {}, set()
    for item in report['elements']:
        instance, label = item.get('instance'), item.get('element_label')
        if not isinstance(instance, str) or type(label) is not int or label <= 0:
            raise ValueError('Invalid element identity')
        names = by_case.get(instance.upper(), [])
        if len(names) != 1:
            raise ValueError('Missing or ambiguous assembly instance: ' + instance)
        actual = names[0]
        key = (actual, label)
        if key in seen:
            raise ValueError('Duplicate element identity in report')
        seen.add(key)
        grouped.setdefault(actual, set()).add(label)
    for name, labels in grouped.items():
        existing = set(e.label for e in assembly.instances[name].elements)
        missing = labels - existing
        if missing:
            raise ValueError('Missing elements in {}: {}'.format(name, sorted(missing)))
    return tuple((name, tuple(sorted(labels))) for name, labels in sorted(grouped.items()))


def create_diagnostic_set(assembly, report, name='DIAGNOSTIC_DISTORTED', apply=False):
    """Preview by default; optional single assembly-set creation, never saves CAE."""
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,79}', name):
        raise ValueError('Use a 1-80 character alphanumeric/underscore set name')
    if name in assembly.sets:
        raise ValueError('Set already exists; choose a new name')
    selection = prepare_selection(assembly, report)
    if not selection:
        raise ValueError('No supported element findings to select')
    if apply:
        assembly.SetFromElementLabels(name=name, elementLabels=selection)
    return selection
