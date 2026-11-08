"""The manual ChatGPT live test (semasa.chatgpt_test): its picture, and that one failing step does not hide the others."""

import io

from PIL import Image

from semasa import chatgpt_login as cl
from semasa import chatgpt_test as ct


class Login:
    def __init__(self, read="A red circle, a blue square and the text WS 4821", draw_exc=None):
        self.read, self.draw_exc, self.asked = read, draw_exc, []

    def settings(self):
        return {"model": "gpt-6.1-sol"}

    def write(self, system, user, *, model, timeout):
        self.asked.append("write")
        return "Na"

    def read_image(self, system, prompt, data, mime, *, model, timeout):
        self.asked.append("read")
        assert mime == "image/png" and Image.open(io.BytesIO(data)).size == (800, 460)
        return self.read

    def draw(self, prompt, *, model, timeout):
        self.asked.append("draw")
        if self.draw_exc:
            raise self.draw_exc
        buf = io.BytesIO()
        Image.new("RGB", (512, 512), "blue").save(buf, "PNG")
        return buf.getvalue()


def test_the_test_picture_is_a_real_png_with_the_things_a_reader_must_name():
    img = Image.open(io.BytesIO(ct.test_picture())).convert("RGB")
    assert img.size == (800, 460)
    assert img.getpixel((160, 180)) == (220, 30, 30) and img.getpixel((420, 180)) == (30, 60, 220)


def test_all_three_steps_pass_and_the_drawn_picture_is_saved(tmp_path):
    res = ct.run(Login(), tmp_path)
    assert [res[n]["ok"] for n in ("write", "read", "draw")] == [True, True, True]
    assert (tmp_path / "chatgpt-drawn.png").exists() and "512x512" in res["draw"]["detail"] and res["model"] == "gpt-6.1-sol"


def test_a_wrong_reading_and_a_refused_draw_are_reported_and_do_not_stop_the_other_steps(tmp_path):
    lg = Login(read="I see a picture", draw_exc=cl.ChatGPTError("usage limit reached", limit=True))
    res = ct.run(lg, tmp_path)
    assert res["write"]["ok"] and not res["read"]["ok"] and not res["draw"]["ok"]
    assert "usage limit" in res["draw"]["detail"] and lg.asked == ["write", "read", "draw"]
    assert not (tmp_path / "chatgpt-drawn.png").exists()
