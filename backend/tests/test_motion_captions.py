from semasa import motion


def test_actual_word_captions_group_two_to_four_words():
    scenes = [{'id':'s1', 'start':1, 'duration':5, 'audio':'assets/voice.mp3', 'audio_s':4,
               'narration':'One two three four five six',
               'words':[[i*.4, i*.4+.3, w] for i,w in enumerate('One two three four five six'.split())]}]
    cues = motion.caption_cues(scenes)
    assert [len(c['text'].split()) for c in cues] == [3,3]
    assert all(c['timing'] == 'actual-word' for c in cues)
    assert cues[0]['start'] == 1 and cues[-1]['end'] == 3.3


def test_missing_alignment_is_phrase_fallback_honestly_estimated():
    scenes = [{'id':'s1', 'start':0, 'duration':5, 'audio':'assets/voice.mp3', 'audio_s':4,
               'narration':'This is one complete sentence.', 'words':[]}]
    cues = motion.caption_cues(scenes)
    assert len(cues) == 1 and cues[0]['timing'] == 'estimated-phrase'
    assert cues[0]['text'] == scenes[0]['narration']
    html = motion.inject_layers('<div id="root" data-duration="5"></div>', scenes, 5, 1080, 1920, False)
    assert 'data-caption-timing="estimated-phrase"' in html
    assert 'background:transparent' in html


def test_silent_and_outro_have_no_duplicate_captions():
    assert motion.caption_cues([{'id':'s1', 'narration':'Read this.', 'words':[]}]) == []
    assert motion.caption_cues([{'id':'brand-outro', 'audio':'x', 'narration':'Follow us for more'}]) == []
