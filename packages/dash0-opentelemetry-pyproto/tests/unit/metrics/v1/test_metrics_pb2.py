from opentelemetry._proto.metrics.v1.metrics_pb2 import _sfixed64


def test_sfixed64_zero_is_omitted() -> None:
    assert _sfixed64(1, 0) == b""


def test_sfixed64_none_is_omitted_like_zero() -> None:
    assert _sfixed64(1, None) == b""


def test_sfixed64_negative_one() -> None:
    assert _sfixed64(1, -1) == b"\x09\xff\xff\xff\xff\xff\xff\xff\xff"
