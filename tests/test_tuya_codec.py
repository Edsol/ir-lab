from ir_lab.tuya_codec import decode_tuya_ir, encode_tuya_ir, parse_raw_text


def test_encode_decode_roundtrip_literal_blocks():
    raw = [9000, 4500, 600, 600, 600, 1680, 600, 600, 600, 20000]
    encoded = encode_tuya_ir(raw)
    assert decode_tuya_ir(encoded) == raw


def test_parse_raw_text():
    assert parse_raw_text("[9000, 4500, 600, 1680]") == [9000, 4500, 600, 1680]


def test_decode_known_sample_prefix():
    code = (
        "CUsjhRFhApgGYQLAAUAL4AMDQAGADwCeYAfgHwEBmAbgAQPgBwFAG0ABwAdAAcALA5pO"
        "YQLAC+AjAeArM+AHAQeYBmECmAZhAg=="
    )
    raw = decode_tuya_ir(code)
    assert raw[:10] == [9035, 4485, 609, 1688, 609, 609, 609, 609, 609, 1688]
    assert len(raw) > 100
