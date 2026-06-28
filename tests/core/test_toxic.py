"""core.detect_toxic_patterns 규격 테스트 — 독소조항 임계 필터 (고도화 B)."""
from contracts.enums import ToxicPattern
from core import detect_toxic_patterns


def test_임계치_이상만_점수순으로():
    matches = [
        (ToxicPattern.IP_TOTAL_FREE, 0.9),
        (ToxicPattern.NONCOMPETE_EXCESS, 0.3),
        (ToxicPattern.PAYMENT_DELAY_UNFAIR, 0.7),
    ]
    result = detect_toxic_patterns(matches, threshold=0.5)
    # 0.3 은 탈락, 나머지는 점수 내림차순
    assert result == [ToxicPattern.IP_TOTAL_FREE, ToxicPattern.PAYMENT_DELAY_UNFAIR]


def test_모두_미달이면_빈결과():
    matches = [(ToxicPattern.IP_TOTAL_FREE, 0.2)]
    assert detect_toxic_patterns(matches, threshold=0.5) == []


def test_빈_입력은_빈결과():
    assert detect_toxic_patterns([], threshold=0.5) == []
