from semasa import motion_layout, motion_styles


def test_recipe_does_not_claim_estimates_are_actual_sentence_alignment():
    plan = motion_styles.complete_plan({'options':{'style':'styles-editorial-explainer'}})
    assert 'estimated' in plan['caption_timing']
    assert 'word' in plan['caption_timing']


def test_actual_word_captions_are_small_and_follow_recording():
    sc = {'start':10,'duration':8,'audio_s':6,'narration':'One two three four five six seven eight',
          'words':[[i*.7,i*.7+.5,w] for i,w in enumerate('One two three four five six seven eight'.split())],
          'timing_source':'actual-word'}
    chunks = motion_layout.caption_chunks(sc)
    assert all(2 <= len(text.split()) <= 4 for text,_,_ in chunks)
    assert chunks[0][1] == 10 and chunks[-1][2] == 15.4


def test_untrusted_spread_words_do_not_become_karaoke():
    sc = {'start':0,'duration':8,'audio_s':6,'narration':'One two three four five six seven eight',
          'words':[[100,101,w] for w in 'One two three four five six seven eight'.split()],
          'timing_source':'estimated-phrase'}
    chunks = motion_layout.caption_chunks(sc)
    assert all(0 <= start < end <= 6 for _,start,end in chunks)
