"""M09: typed identifier pronunciation stays atomic through sentence chunking."""
import re

DIGITS = ['صفر', 'واحد', 'اثنان', 'ثلاثة', 'أربعة', 'خمسة', 'ستة', 'سبعة', 'ثمانية', 'تسعة']


def _segments(text: str, slots=None):
    if not isinstance(text, str) or not text or len(text) > 4000:
        raise ValueError('TTS text must contain 1..4000 characters')
    slots = [] if slots is None else slots
    if not isinstance(slots, list) or len(slots) > 20:
        raise ValueError('invalid pronunciation slots')
    replacements = {}
    for slot in slots:
        if not isinstance(slot, dict) or slot.get('kind') != 'id':
            raise ValueError('only typed identifier slots implemented')
        value = slot.get('value')
        if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,30}', value) or value in replacements:
            raise ValueError('invalid/duplicate identifier')
        if not re.search(r'(?<!\w)'+re.escape(value)+r'(?!\w)', text):
            raise ValueError('identifier not found in reply')
        replacements[value] = ' '.join(DIGITS[int(d)] for d in value)
    text = re.sub(r'[\x00-\x08\x0b-\x1f]', '', text).strip()
    if not replacements:
        return [(text, False)]
    pattern = re.compile(r'(?<!\w)('+'|'.join(map(re.escape, replacements))+r')(?!\w)')
    out, pos = [], 0
    for match in pattern.finditer(text):
        out += [(text[pos:match.start()], False), (replacements[match.group()], True)]
        pos = match.end()
    out.append((text[pos:], False))
    return out


def prepare_speech(text: str, slots=None) -> str:
    """Display remains literal; dates/amounts require a business pronunciation table."""
    return ''.join(value for value, _ in _segments(text, slots))


def speech_chunks(text: str, slots=None, limit=180) -> list[str]:
    if not isinstance(limit, int) or limit < 1:
        raise ValueError('invalid chunk limit')
    out, current = [], ''
    for segment, protected in _segments(text, slots):
        units = [segment] if protected else re.findall(r'\S+|\s+', segment)
        for unit in units:
            if not unit or unit.isspace():
                if current and not current.endswith(' '):
                    current += ' '
                continue
            if len(unit) > limit:
                raise ValueError('protected token exceeds chunk limit')
            if len(current)+len(unit) > limit:
                if current.strip():
                    out.append(current.strip())
                current = ''
            current += unit
            if not protected and re.search(r'[.!?؟؛]$', unit):
                out.append(current.strip())
                current = ''
    if current.strip():
        out.append(current.strip())
    if not out:
        raise ValueError('empty normalized TTS text')
    return out


def chunks(text: str, limit=180) -> list[str]:
    return speech_chunks(text, limit=limit)
