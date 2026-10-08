import sys_memory_report as mod


def test_plugin_meta():
    meta = mod.PLUGIN_META
    assert meta["name"] == "sys_memory_report"
    assert isinstance(meta["description"], str) and meta["description"]
    assert isinstance(meta["version"], str) and meta["version"]


def test_human_format():
    assert mod._human(0) == "0.00 B"
    assert mod._human(1024) == "1.00 KB"
    assert mod._human(1536 * 1024) == "1.50 MB"
    assert mod._human(1024 ** 3) == "1.00 GB"
    assert mod._human(None) == "未知"


def test_parse_size():
    assert mod._parse_size("2048.00M") == 2048 * 1024 ** 2
    assert mod._parse_size("1.5G") == int(1.5 * 1024 ** 3)
    assert mod._parse_size("512K") == 512 * 1024
    assert mod._parse_size("garbage") == 0


def test_run_returns_sane_memory_info():
    result = mod.run()
    assert isinstance(result, dict)
    assert result["success"] is True, result
    assert result["total_bytes"] > 0
    assert result["used_bytes"] >= 0
    assert result["available_bytes"] >= 0
    assert result["used_bytes"] <= result["total_bytes"]
    assert 0 <= result["used_percent"] <= 100
    assert result["used_human"].endswith(("B", "KB", "MB", "GB", "TB", "PB"))
    assert isinstance(result["summary"], str) and result["summary"]
    assert "内存总量" in result["summary"]


def test_swap_fields_present():
    result = mod.run()
    assert result["swap_total_bytes"] >= 0
    assert result["swap_used_bytes"] >= 0
    assert result["swap_used_bytes"] <= result["swap_total_bytes"]
    assert 0 <= result["swap_used_percent"] <= 100


def test_build_helper_math():
    built = mod._build(1000, 250, 750, swap_total=100, swap_free=40, source="unit-test")
    assert built["used_percent"] == 25.0
    assert built["swap_used_bytes"] == 60
    assert built["swap_used_percent"] == 60.0
    assert built["source"] == "unit-test"


def test_run_never_raises_on_unknown_kwargs():
    result = mod.run(unused_option=True)
    assert isinstance(result, dict)
    assert "success" in result
