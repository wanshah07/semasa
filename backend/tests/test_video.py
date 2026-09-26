"""Video: a long talk read into words, clips proposed by the writer, and a clip cut to a 9:16 short with captions that
becomes a draft post. The cutting is real (the static ffmpeg from the pip wheel, on a generated test video); YouTube
itself is never called here."""

import subprocess

import pytest
from fakestore import FakeStore
from test_studio_cards import _settings

from semasa import media_generator, video

AUTO_VTT = """WEBVTT
Kind: captions
Language: ms

00:00:00.000 --> 00:00:02.500 align:start position:0%
assalamualaikum<00:00:00.800><c> tuan</c><c> puan</c>

00:00:02.500 --> 00:00:02.510 align:start position:0%
assalamualaikum tuan puan

00:00:02.510 --> 00:00:05.000 align:start position:0%
assalamualaikum tuan puan
hari<00:00:03.100><c> ini</c><c> kita</c><c> bincang</c>

00:00:05.000 --> 00:00:08.000 align:start position:0%
hari ini kita bincang
soal<c> halal</c> &amp; haram
"""

PASTED = """0:00
Assalamualaikum tuan-tuan dan puan-puan
0:04
hari ini kita bincang soal
makanan yang diragui
1:02:03 penutup majlis"""


def test_youtube_links_are_recognised():
    for u in ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "https://youtu.be/dQw4w9WgXcQ?t=30",
              "https://www.youtube.com/watch?feature=share&v=dQw4w9WgXcQ", "https://youtube.com/shorts/dQw4w9WgXcQ",
              "https://www.youtube.com/live/dQw4w9WgXcQ"):
        assert video.youtube_id(u) == "dQw4w9WgXcQ"
    assert video.youtube_id("https://example.com/v.mp4") is None


def test_times_read_and_written():
    assert video.parse_ts("1:02:03") == 3723 and video.parse_ts("12:34") == 754 and video.parse_ts(75) == 75
    assert video.parse_ts("abc") is None and video.fmt_ts(3723) == "1:02:03" and video.fmt_ts(75) == "1:15"


def test_automatic_captions_lose_their_rolling_repeats_and_tags():
    segs = video.parse_vtt(AUTO_VTT)
    assert [s["t"] for s in segs] == ["assalamualaikum tuan puan", "hari ini kita bincang", "soal halal & haram"]
    assert segs[0]["s"] == 0 and segs[-1]["e"] == 8


def test_a_pasted_youtube_transcript_is_read_with_its_times():
    segs = video.parse_pasted(PASTED)
    assert [s["s"] for s in segs] == [0, 4, 3723]
    assert segs[1]["t"] == "hari ini kita bincang soal makanan yang diragui" and segs[0]["e"] == 4


def test_the_captions_track_is_chosen_sensibly():
    info = {"language": "ms", "subtitles": {},
            "automatic_captions": {"en": [{"ext": "vtt", "url": "E"}],
                                   "ms-orig": [{"ext": "json3", "url": "x"}, {"ext": "vtt", "url": "M"}]}}
    assert video.pick_captions(info) == ("M", "auto-captions", "ms-orig")
    info["subtitles"] = {"ms": [{"ext": "vtt", "url": "S"}]}
    assert video.pick_captions(info)[:2] == ("S", "subtitles")
    assert video.pick_captions({"subtitles": {}, "automatic_captions": {}}) is None


SEGS = [{"s": float(i * 5), "e": float(i * 5 + 5), "t": f"ayat {i}"} for i in range(40)]


def test_proposed_clips_are_kept_inside_the_rules():
    raw = [{"start": "0:09", "end": "0:41", "title": "t", "hook": "h", "caption": "c"},     # snapped to 10–40
           {"start": "0:10", "end": "0:20"},                                                # 10 s: too short
           {"start": "1:00", "end": "2:40"},                                                # 100 s: too long
           {"start": "3:10", "end": "9:00"},                                                # past the end
           {"start": "x", "end": "y"}, "junk"]
    out = video.validate_clips(raw, SEGS, 200)
    assert len(out) == 1 and out[0]["start"] == 10 and out[0]["end"] == 40


class Writer:
    configured = True
    last_model = "m"

    def __init__(self, out):
        self.out, self.seen = out, []

    def why_off(self):
        return "off"

    def chat_json(self, system, user, max_tokens=0, **k):
        self.seen.append((system, user))
        return self.out


def _vstore(**v):
    row = {"id": "v1", "source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "source_kind": "youtube",
           "stream": "regulab", "status": "new", "attempts": 0, "note": "", "transcript_paste": None, **v}
    return FakeStore(semasa_videos=[row], semasa_settings=[], semasa_posts=[], media_generations=[], semasa_log=[])


def test_a_youtube_refusal_with_a_pasted_transcript_still_reads(monkeypatch):
    def refused(url):
        raise video._youtube_refusal(RuntimeError("Sign in to confirm you're not a bot"))
    monkeypatch.setattr(video, "read_youtube", refused)
    w = Writer({"clips": [{"start": "0:00", "end": "0:30", "title": "T", "hook": "H", "caption": "C"}], "speaker": "Ustaz A"})
    store = _vstore(transcript_paste="\n".join(f"0:{i*5:02d}\nayat {i}" for i in range(10)))
    assert video.run(store, w) == "Video: 1/1 read"
    v = store.tables["semasa_videos"][0]
    assert v["status"] == "ready" and v["transcript_source"] == "pasted" and v["clips"][0]["speaker"] == "Ustaz A"
    system, user = w.seen[0]
    assert "Never change what the speaker meant" in system and "never the words YouTube" in system
    assert "[0:00] ayat 0 ayat 1" in user


def test_a_refusal_with_nothing_pasted_says_how_to_get_round_it(monkeypatch):
    monkeypatch.setattr(video, "read_youtube", lambda url: (_ for _ in ()).throw(
        video._youtube_refusal(RuntimeError("Sign in to confirm you're not a bot"))))
    store = _vstore()
    video.run(store, Writer({}))
    v = store.tables["semasa_videos"][0]
    assert v["status"] == "error" and "Paste the transcript" in v["error"] and "Google Drive" in v["error"]


def test_no_table_yet_is_a_line_not_a_crash():
    class Broken:
        def table(self, name):
            raise RuntimeError('relation "semasa_videos" does not exist')
    assert "011_video.sql" in video.run(Broken(), Writer({}))


# --- the cut --------------------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def talk(tmp_path_factory):
    """A 40-second 1920x1080 'talk' with a tone, made by the same ffmpeg."""
    path = tmp_path_factory.mktemp("v") / "talk.mp4"
    subprocess.run([video.ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc2=size=1920x1080:rate=30:duration=40", "-f", "lavfi", "-i", "sine=frequency=440:duration=40",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(path)], check=True)
    return path


@pytest.mark.parametrize("frame", ["fit", "fill"])
def test_a_clip_is_cut_to_a_captioned_9_16_short(talk, tmp_path, frame):
    out = tmp_path / "clip.mp4"
    ass = video.build_ass(SEGS, 10, 30, "Hukum makanan *yang* diragui {test}")
    assert "Dialogue: 1,0:00:00.00,0:00:20.00,Hook" in ass and "(test)" in ass
    video.render(talk, out, start_in_file=10, dur=20, ass_text=ass, frame=frame, stream="regulab")
    p = subprocess.run([video.ffmpeg(), "-hide_banner", "-i", str(out)], capture_output=True, text=True)
    assert "1080x1920" in p.stderr and "Audio: aac" in p.stderr
    assert abs(video.probe_duration(out) - 20) < 0.5
    assert out.stat().st_size < video.MAX_OUT_BYTES


def test_captions_really_reach_the_picture(talk, tmp_path):
    """The same frame with and without the words must differ: a silent libass or font failure would not."""
    frames = []
    for words in (True, False):
        out = tmp_path / f"c{words}.mp4"
        video.render(talk, out, start_in_file=10, dur=4, ass_text=video.build_ass(SEGS, 10, 14, "", captions=words),
                     frame="fit", stream="linkedin")
        jpg = tmp_path / f"c{words}.jpg"
        subprocess.run([video.ffmpeg(), "-loglevel", "error", "-y", "-ss", "1", "-i", str(out), "-frames:v", "1", str(jpg)],
                       check=True)
        frames.append(jpg.read_bytes())
    assert frames[0] != frames[1]


def _clip_store(rights="own", post_id=None):
    v = {"id": "v1", "source_url": "https://example.com/talk.mp4", "source_kind": "link", "stream": "regulab",
         "domain": "fatwa", "rights": rights, "title": "Ceramah Halal", "channel": "Ustaz A", "transcript": SEGS}
    job = {"id": "c1", "mode": "clip", "type": "video", "status": "processing", "attempts": 1, "created_by": "u",
           "post_id": post_id,
           "meta": {"video_id": "v1", "start": 10, "end": 30, "hook": "Hukum makanan diragui",
                    "caption": "Ustaz A menerangkan hukum makanan yang diragui.", "speaker": "Ustaz A", "frame": "fit"}}
    return FakeStore(semasa_videos=[v], media_generations=[job], semasa_settings=[], semasa_log=[],
                     semasa_posts=[{"id": "p9", "status": "draft", "media_ids": ["old"]}],)


def test_an_approved_clip_is_cut_stored_and_becomes_a_draft_post(talk, monkeypatch):
    got = {}
    monkeypatch.setattr(video, "fetch_section", lambda v, s, e, work: (talk, s))
    monkeypatch.setattr(media_generator.db, "upload_generated", lambda store, path, data, ct: got.setdefault(path, ct) and f"https://cdn/{path}")
    store = _clip_store()
    assert media_generator.process_row(store, store.tables["media_generations"][0], _settings(), {}, None) is True
    job = store.tables["media_generations"][0]
    assert job["status"] == "done" and job["generated_media_url"].endswith("-clip.mp4") and job["meta"]["poster_url"]
    assert sorted(got.values()) == ["image/jpeg", "video/mp4"]
    post = next(p for p in store.tables["semasa_posts"] if p["id"] != "p9")
    assert post["status"] == "draft" and post["media_ids"] == ["c1"] and post["citation"].startswith("Ustaz A")
    assert post["text"]["bm"]["instagram"].startswith("Ustaz A menerangkan") and job["post_id"] == post["id"]


def test_no_rights_no_cut(talk, monkeypatch):
    monkeypatch.setattr(video, "fetch_section", lambda *a: pytest.fail("must not fetch without rights"))
    store = _clip_store(rights=None)
    assert media_generator.process_row(store, store.tables["media_generations"][0], _settings(), {}, None) is False
    job = store.tables["media_generations"][0]
    assert job["status"] == "error" and "no rights recorded" in job["error"]


def test_a_recut_replaces_the_old_clip_in_its_own_draft(talk, monkeypatch):
    monkeypatch.setattr(video, "fetch_section", lambda v, s, e, work: (talk, s))
    monkeypatch.setattr(media_generator.db, "upload_generated", lambda store, path, data, ct: f"https://cdn/{path}")
    store = _clip_store(post_id="p9")
    store.tables["media_generations"].append({"id": "old", "mode": "clip", "status": "done"})
    media_generator.process_row(store, store.tables["media_generations"][0], _settings(), {}, None)
    assert next(p for p in store.tables["semasa_posts"] if p["id"] == "p9")["media_ids"] == ["c1"]
    assert len(store.tables["semasa_posts"]) == 1                          # no second post
