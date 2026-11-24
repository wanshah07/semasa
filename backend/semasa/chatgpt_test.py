"""A manual, live test of Wan's ChatGPT login (Wan, 8 Nov 2026: "test chatgpt read and generate image"): one short answer, one
picture READ and one picture DRAWN, each through the real Codex backend with the saved tokens. Run by chatgpt-test.yml (manual
only, no schedule). It spends one ChatGPT image allowance, writes nothing to the database except a refreshed token and a model the
account allows (exactly what any other call does), and saves the drawn picture to a folder the workflow uploads for Wan.

    python -m semasa.chatgpt_test [output_dir]
"""

from __future__ import annotations

import io
import logging
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from . import chatgpt_login as cl
from . import db

log = logging.getLogger("semasa.chatgpt_test")

TEXT_ON_PICTURE = "WS 4821"
DRAW_PROMPT = "A flat vector icon of a laboratory flask with blue liquid on a plain white background, no text"
MODE_IMAGE_MODELS = "chatgpt_image_models"          # settings.ai_test.what, or the workflow's `mode` input


def test_picture() -> bytes:
    """A picture with three things a reader must get right: a red circle, a blue square and the text WS 4821."""
    img = Image.new("RGB", (800, 460), "white")
    d = ImageDraw.Draw(img)
    d.ellipse((60, 80, 260, 280), fill=(220, 30, 30))
    d.rectangle((320, 80, 520, 280), fill=(30, 60, 220))
    try:
        font = ImageFont.load_default(size=70)
    except TypeError:                       # an older Pillow has one fixed size
        font = ImageFont.load_default()
    d.text((60, 320), TEXT_ON_PICTURE, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def run(login: Any, out_dir: Path | None = None, draw_model: str = "") -> dict[str, Any]:
    """{write, read, draw: {ok, detail}, model}. Each step is tried on its own, so one failure does not hide the others."""
    results: dict[str, Any] = {}

    def step(name: str, fn: Any) -> None:
        try:
            ok, detail = fn()
        except cl.ChatGPTError as exc:
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001 - report it, then carry on to the next step
            ok, detail = False, f"{type(exc).__name__}: {str(exc)[:300]}"
        results[name] = {"ok": bool(ok), "detail": detail}
        log.info("%s: %s %s", name, "OK" if ok else "FAILED", detail)

    model = str((login.settings() or {}).get("model") or cl.DEFAULT_MODEL)

    def write() -> tuple[bool, str]:
        out = login.write("Answer in one short sentence.", "What is the chemical symbol for sodium?", model=model, timeout=90)
        return "na" in out.lower(), out.strip()[:200]

    def read() -> tuple[bool, str]:
        out = login.read_image("Describe pictures exactly and briefly.",
                               "List the shapes with their colours and copy any text you can read.",
                               test_picture(), "image/png", model=model, timeout=120)
        low = out.lower()
        return ("red" in low and "blue" in low and "4821" in low), out.strip()[:300]

    def draw() -> tuple[bool, str]:
        # a pinned PICTURE model (gpt-image-2...) is the image tool's own model; a pinned chat model is the one calling the tool
        tool = draw_model if cl.IMAGE_TOOL_RE.search(draw_model or "") else ""
        data = login.draw(DRAW_PROMPT, model=model if tool else (draw_model or model), timeout=280,
                          **({"image_model": tool} if tool else {}))
        img = Image.open(io.BytesIO(data))
        img.load()
        if out_dir is not None:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "chatgpt-drawn.png").write_bytes(data)
        return min(img.size) >= 256, f"{img.format} {img.size[0]}x{img.size[1]}, {len(data)} bytes"

    step("write", write)
    step("read", read)
    step("draw", draw)
    results["model"] = str((login.settings() or {}).get("model") or model)      # the model that finally answered, if it moved
    results["draw_model"] = draw_model or results["model"]                       # the one the picture was asked of
    return results


def probe_image_models(login: Any, candidates: tuple[str, ...] = cl.IMAGE_TOOL_MODELS) -> dict[str, Any]:
    """Which PICTURE models this ChatGPT login draws with (Wan, 24 Nov 2026: "check why chatgpt not list out image gen model such
    as gpt-image-2"). Each candidate is asked for ONE small real picture, with no fallback, through the login's own chat model:
    a refusal costs nothing, a picture costs one of the plan's picture allowances. A candidate counts only when a real picture
    came back AND, where the drawn item names its model, that name is the candidate (a server that ignores the field and draws
    with its default must not pass for the model asked). A used-up allowance stops the probe: the rest stay untried.
    Returns {chat_model, tried: {candidate: {ok, error | said}}, models: [accepted]}."""
    chat = str((login.settings() or {}).get("model") or cl.DEFAULT_MODEL)
    tried: dict[str, Any] = {}
    for cand in candidates:
        said: dict[str, Any] = {}
        try:
            data = login.draw_once(DRAW_PROMPT, model=chat, image_model=cand, info=said)
            img = Image.open(io.BytesIO(data))
            img.load()
            named = str(said.get("model") or "")
            same = not named or named == cand or named.startswith(cand + "-")
            tried[cand] = {"ok": bool(same and min(img.size) >= 256), "said": said, "size": f"{img.size[0]}x{img.size[1]}",
                           **({} if same else {"error": f"ChatGPT drew with {named}, not {cand}"})}
        except cl.ChatGPTError as exc:
            tried[cand] = {"ok": False, "error": str(exc)[:240]}
            if exc.limit:
                log.info("picture-model probe stopped at %s: the picture allowance is used up", cand)
                break
        except Exception as exc:  # noqa: BLE001 - one candidate's failure is its own
            tried[cand] = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        log.info("picture model %s: %s", cand, "DRAWS" if tried[cand]["ok"] else "no: " + str(tried[cand].get("error")))
    return {"chat_model": chat, "tried": tried, "models": [c for c, v in tried.items() if v.get("ok")]}


def record_image_models(res: dict[str, Any], store: Any) -> dict[str, Any]:
    """The probe's answer where the workers and the page read it: settings[chatgpt_image_models] = {at, chat_model, tried,
    models}, and settings.ai_test_result so the API tab's card shows what happened. A probe that tried nothing keeps the last
    good list."""
    from datetime import UTC, datetime
    at = datetime.now(UTC).isoformat()
    value = {"at": at, **res}
    try:
        if res.get("tried"):
            store.table(db.SETTINGS).upsert({"key": cl.IMAGE_MODELS_KEY, "value": value}, on_conflict="key").execute()
        store.table(db.SETTINGS).upsert({"key": "ai_test_result", "value": {
            "at": at, "what": MODE_IMAGE_MODELS, "ok": bool(res.get("models")), "models": res.get("models") or [],
            "steps": {c: {"ok": bool(v.get("ok")), "detail": str(v.get("error") or v.get("size") or "")[:200]}
                      for c, v in (res.get("tried") or {}).items()}}}, on_conflict="key").execute()
    except Exception as exc:  # noqa: BLE001 - the log still has it
        log.info("picture models not recorded (%s)", str(exc)[:120])
    return value


def wanted_mode(store: Any, argv: list[str]) -> str:
    """"chatgpt_image_models" when the workflow's mode input, or the page's request (settings.ai_test.what), asks for the
    picture-model probe; else "" (the ordinary write, read, draw test)."""
    import os
    if MODE_IMAGE_MODELS in argv or os.environ.get("CHATGPT_TEST_MODE", "").strip() == "image-models":
        return MODE_IMAGE_MODELS
    try:
        rows = store.table(db.SETTINGS).select("value").eq("key", "ai_test").execute().data or []
        req = (rows[0].get("value") or {}) if rows else {}
    except Exception:  # noqa: BLE001 - no request is the ordinary test
        return ""
    return MODE_IMAGE_MODELS if os.environ.get("GITHUB_EVENT_NAME") == "repository_dispatch" and \
        req.get("what") == MODE_IMAGE_MODELS else ""


def pinned_draw_model(store: Any) -> str:
    """The model Wan pinned for the picture maker when that pin is on ChatGPT, else "" (the login's saved model draws)."""
    try:
        from . import ai_team
        pin = ai_team.read_pins(store).get("image_gen") or {}
    except Exception:  # noqa: BLE001 - no pin is the saved model
        return ""
    return str(pin.get("model") or "") if pin.get("gateway") == "chatgpt" else ""


def record(res: dict[str, Any], store: Any | None = None) -> dict[str, Any]:
    """The result where the API tab reads it (settings.ai_test_result): ok, the three steps' words, the model and the time. Never
    raises: the test's own answer is the log, the record is for the page (Wan, 24 Nov 2026: "button so we can test ... live")."""
    from datetime import UTC, datetime
    value = {"at": datetime.now(UTC).isoformat(), "what": "chatgpt", "model": res.get("model"),
             "draw_model": res.get("draw_model") or res.get("model"),
             "ok": all((res.get(n) or {}).get("ok") for n in ("write", "read", "draw")),
             "steps": {n: {"ok": bool((res.get(n) or {}).get("ok")), "detail": str((res.get(n) or {}).get("detail") or "")[:200]}
                       for n in ("write", "read", "draw")}}
    try:
        (store or db.client()).table(db.SETTINGS).upsert({"key": "ai_test_result", "value": value}, on_conflict="key").execute()
    except Exception as exc:  # noqa: BLE001 - the log still has it
        log.info("ai_test_result not written (%s)", str(exc)[:120])
    return value


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    login = cl.Login(db.client())
    if not login.connected():
        print("RESULT not connected: log in on the API page first")
        from datetime import UTC, datetime
        try:
            db.client().table(db.SETTINGS).upsert({"key": "ai_test_result", "value": {
                "at": datetime.now(UTC).isoformat(), "what": "chatgpt", "ok": False, "not_connected": True,
                "steps": {}}}, on_conflict="key").execute()
        except Exception as exc:  # noqa: BLE001
            log.info("ai_test_result not written (%s)", str(exc)[:120])
        return 1
    store = db.client()
    if wanted_mode(store, sys.argv) == MODE_IMAGE_MODELS:
        found = record_image_models(probe_image_models(login), store)
        for cand, v in (found.get("tried") or {}).items():
            what = v.get("error") or v.get("size")
            print(f"RESULT {cand}={'DRAWS' if v.get('ok') else 'no'} · {what} · said {v.get('said') or {}}")
        print(f"RESULT picture models={', '.join(found.get('models') or []) or 'none'}")
        return 0
    res = run(login, out_dir, pinned_draw_model(store))
    record(res, store)
    for name in ("write", "read", "draw"):
        print(f"RESULT {name}={'OK' if res[name]['ok'] else 'FAILED'} · {res[name]['detail']}")
    print(f"RESULT model={res['model']}")
    return 0 if all(res[n]["ok"] for n in ("write", "read", "draw")) else 1


if __name__ == "__main__":
    sys.exit(main())
