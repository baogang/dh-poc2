"""M13: reproducible micro WER/CER and confusion metrics; no semantic guessing."""
import re
import unicodedata


def normalize(text: str, arabic: bool = True) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    if arabic:
        text = re.sub(r"[\u064b-\u065f\u0670\u0640]", "", text)
        text = text.translate(str.maketrans("أإآٱى", "ااااي"))
    # Keep English and every digit; do not erase code switching or numbers.
    text = "".join(c if c.isalnum() or c.isspace() else " " for c in text)
    return " ".join(text.split())


def edit_counts(reference, hypothesis) -> dict:
    """Deterministic Levenshtein backtrace, recording S/D/I separately."""
    n, m = len(reference), len(hypothesis)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            dp[i][j] = min(dp[i-1][j]+1, dp[i][j-1]+1, dp[i-1][j-1]+(reference[i-1] != hypothesis[j-1]))
    i, j, s, d, ins = n, m, 0, 0, 0
    while i or j:
        if i and j and dp[i][j] == dp[i-1][j-1] + (reference[i-1] != hypothesis[j-1]):
            s += reference[i-1] != hypothesis[j-1]
            i, j = i-1, j-1
        elif i and dp[i][j] == dp[i-1][j]+1:
            d += 1
            i -= 1
        else:
            ins += 1
            j -= 1
    return {"substitutions": s, "deletions": d, "insertions": ins, "reference_units": n,
            "error_rate": (s+d+ins)/n if n else (0.0 if not m else None)}


def score(reference: str, hypothesis: str) -> dict:
    r, h = normalize(reference), normalize(hypothesis)
    return {"wer": edit_counts(r.split(), h.split()),
            "cer": edit_counts(r.replace(" ", ""), h.replace(" ", "")),
            "strict_wer": edit_counts(reference.split(), hypothesis.split())}


def confusion(tp: int, fp: int, fn: int, tn: int) -> dict:
    return {"precision": tp/(tp+fp) if tp+fp else None,
            "recall": tp/(tp+fn) if tp+fn else None,
            "false_positive_rate": fp/(fp+tn) if fp+tn else None}


def capacity(calls_per_hour=3000, aht_seconds=300, peak=2, asr_duty=.35, tts_duty=.25):
    calls = calls_per_hour / 3600 * aht_seconds * peak
    return {"concurrent_calls": calls, "asr_active_equivalents": calls*asr_duty,
            "tts_active_equivalents": calls*tts_duty}
