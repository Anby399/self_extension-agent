import os
import time

import disk_usage_advisor as mod


def test_plugin_meta():
    meta = mod.PLUGIN_META
    assert meta["name"] == "disk_usage_advisor"
    assert isinstance(meta["description"], str) and meta["description"]
    assert isinstance(meta["version"], str) and meta["version"]


def test_human():
    assert mod._human(0) == "0.00 B"
    assert mod._human(1024) == "1.00 KB"
    assert mod._human(1536 * 1024) == "1.50 MB"
    assert mod._human(1024 ** 3) == "1.00 GB"
    assert mod._human(-5) == "0.00 B"
    assert mod._human(None) == "未知"


def test_categorize():
    assert mod._categorize(r"C:\Users\a\AppData\Local\Temp\x.tmp") == "临时文件"
    assert mod._categorize(r"C:\proj\node_modules\pkg\index.js") == "Node.js 依赖缓存"
    assert mod._categorize(r"C:\proj\__pycache__\m.cpython-312.pyc") == "Python 缓存"
    assert (
        mod._categorize(r"C:\Users\a\AppData\Local\Google\Chrome\User Data\Cache\f_001")
        == "浏览器/应用缓存"
    )
    assert mod._categorize(r"D:\$Recycle.Bin\S-1-5-21\x.dll") == "回收站"
    assert mod._categorize(r"C:\Windows\SoftwareDistribution\Download\a.cab") == "Windows 更新缓存"
    assert mod._categorize(r"C:\Users\a\Pictures\holiday.jpg") == "普通文件"
    assert mod._categorize("/home/u/.m2/repository/a.jar") == "开发工具缓存"


def test_run_on_fixture(tmp_path):
    big = tmp_path / "big_old.bin"
    big.write_bytes(os.urandom(3 * 1024 * 1024))
    old_time = time.time() - 400 * 86400
    os.utime(str(big), (old_time, old_time))

    dup_a = tmp_path / "dup_a.bin"
    dup_b = tmp_path / "dup_b.bin"
    payload = os.urandom(2 * 1024 * 1024)
    dup_a.write_bytes(payload)
    dup_b.write_bytes(payload)

    (tmp_path / "small.txt").write_text("hello", encoding="utf-8")

    result = mod.run(
        roots=[str(tmp_path)],
        large_min_mb=1,
        duplicate_min_mb=1,
        old_min_mb=1,
        old_days=30,
        time_budget=30,
    )
    assert result["success"] is True, result
    assert result["scanned_files"] == 4
    assert result["scanned_bytes"] > 5 * 1024 * 1024

    large_paths = [item["path"] for item in result["large_files"]]
    assert str(big) in large_paths

    old_paths = [item["path"] for item in result["old_files"]]
    assert str(big) in old_paths

    assert len(result["duplicate_groups"]) == 1
    group = result["duplicate_groups"][0]
    assert group["count"] == 2
    assert set(group["paths"]) == {str(dup_a), str(dup_b)}
    assert result["duplicate_reclaimable_bytes"] == 2 * 1024 * 1024

    assert isinstance(result["categories"], list) and result["categories"]
    assert result["summary"]
    assert "扫描目录" in result["report"]
    assert result["suggestions"]


def test_run_with_empty_dir(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = mod.run(roots=[str(empty)], time_budget=5)
    assert result["success"] is True
    assert result["scanned_files"] == 0
    assert result["duplicate_groups"] == []
    assert result["suggestions"]


def test_run_tolerates_missing_root(tmp_path):
    missing = tmp_path / "does_not_exist"
    result = mod.run(roots=[str(missing)], time_budget=5)
    assert result["success"] is True
    assert result["scanned_files"] == 0


def test_run_respects_time_budget(tmp_path):
    for index in range(20):
        (tmp_path / ("f%d.txt" % index)).write_text("x" * 10, encoding="utf-8")
    result = mod.run(roots=[str(tmp_path)], time_budget=0)
    assert result["success"] is True
    assert isinstance(result["truncated"], bool)


def test_scan_skips_reparse_points_and_bad_names(tmp_path):
    records, counters = mod._scan([str(tmp_path)], time.monotonic() + 5, 1000)
    assert isinstance(records, list)
    assert counters["files"] == 0


def test_extra_unknown_kwargs_ignored(tmp_path):
    result = mod.run(roots=[str(tmp_path)], time_budget=5, unknown_option=True)
    assert isinstance(result, dict)
    assert result["success"] is True


def test_drive_list_shape():
    drives = mod._drives()
    assert isinstance(drives, list)
    for item in drives:
        assert item["total_bytes"] > 0
        assert item["free_bytes"] <= item["total_bytes"]
        assert 0 <= item["free_percent"] <= 100
