import io
import json

import pytest
from PIL import Image, UnidentifiedImageError
from test_motion import GOOD, NOW, SCRIPT, FakeLLM, Store, _row, _runner

from semasa import motion
from semasa import motion_assets as assets


def image_ref():
    out = io.BytesIO()
    Image.new("RGB", (80, 60), "#287b65").save(out, format="PNG")
    data = out.getvalue()
    return data, {
        "path": "owner/capture.png",
        "mime": "image/png",
        "size": len(data),
        "rights": "self-owned",
        "role": "screenshot",
        "source": "Local test fixture; not production evidence",
        "attribution": "test",
    }


def test_manual_file_preferred_and_injected(tmp_path):
    data, ref = image_ref()
    report = assets.prepare(
        {"created_by": "owner", "options": {"asset_mode": "mixed", "assets": [ref], "effects": ["P01"]}},
        tmp_path,
        download=lambda p: data,
    )
    assert report["effects"][0]["readiness"] == "manualasset"
    out = assets.inject(GOOD, report, [{"duration": 4}], 30)
    assert 'src="assets/manual-0.png"' in out
    assert "Local test fixture" in out
    assert (tmp_path / "assets/manual-0.png").read_bytes().startswith(b"\x89PNG")


@pytest.mark.parametrize(
    "change",
    [
        {"path": "other/capture.png"},
        {"path": "owner/../capture.png"},
        {"mime": "image/svg+xml"},
        {"size": 0},
        {"size": assets.MAX_BYTES + 1},
        {"rights": "unknown"},
    ],
)
def test_private_refs_validate_on_worker(tmp_path, change):
    data, ref = image_ref()
    with pytest.raises(ValueError):
        assets.prepare(
            {"created_by": "owner", "options": {"asset_mode": "manual", "assets": [{**ref, **change}]}},
            tmp_path,
            download=lambda p: data,
        )


def test_mime_spoof_rejected(tmp_path):
    _, ref = image_ref()
    ref["size"] = 12
    with pytest.raises(UnidentifiedImageError):
        assets.prepare(
            {"created_by": "owner", "options": {"asset_mode": "manual", "assets": [ref]}},
            tmp_path,
            download=lambda p: b"not an image",
        )


def test_worker_consumes_prepared_assets_and_reports_fallback(tmp_path):
    store = Store()
    row = _row(store, seconds=30, voice="off", mascot="", language="en", options={"effects": ["B04", "M03", "P03"]})
    assert motion.process(
        store,
        FakeLLM([SCRIPT, {"html": GOOD}]),
        row,
        {"prompt": "", "cli": motion.CLI_VERSION},
        runner=_runner(),
        workdir=tmp_path,
        now=NOW,
    )
    folder = tmp_path / row["id"][:8]
    index = (folder / "index.html").read_text()
    assert 'src="assets/concept.svg"' in index
    assert "Adapted P03" in index
    saved = store.table(motion.TABLE).select("*").eq("id", row["id"]).execute().data[0]
    assert saved["check_report"]["asset_plan"]["effects"][2]["readiness"] == "fallback"
    assert saved["html"] == index
    assert json.loads((folder / "asset-plan.json").read_text())["mode"] == "auto"
