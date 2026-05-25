from ir_lab.raw_analyzer import analyze_raw


def test_analyze_simple_binary_signal():
    raw = [9000, 4500, 600, 600, 600, 1680, 600, 600, 600, 20000, 600, 1680]
    analysis = analyze_raw(raw)
    assert analysis["header"] == [9000, 4500]
    assert len(analysis["frames"]) == 2
    assert analysis["frames"][0]["bits"] == "010"
    assert analysis["frames"][1]["bits"] == "1"
