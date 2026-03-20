from __future__ import annotations

from pathlib import Path


def test_resolve_web_path_falls_back_to_workspace_when_package_assets_are_missing(
    tmp_path: Path, monkeypatch
):
    workspace_root = tmp_path / "workspace"
    static_dir = workspace_root / "kfabric" / "web" / "static"
    static_dir.mkdir(parents=True)
    (static_dir / "style.css").write_text("body {}", encoding="utf-8")

    fake_package_file = tmp_path / "site-packages" / "kfabric" / "web" / "paths.py"
    fake_package_file.parent.mkdir(parents=True)
    fake_package_file.write_text("# test stub\n", encoding="utf-8")

    import kfabric.web.paths as web_paths

    monkeypatch.chdir(workspace_root)
    monkeypatch.setattr(web_paths, "__file__", str(fake_package_file))

    assert web_paths.resolve_web_path("static") == static_dir.resolve()
