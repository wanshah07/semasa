from semasa import motion


def test_worker_owns_transparent_actual_caption_layers():
    scene={'id':'s1','start':0,'duration':3,'audio_s':2,'audio':'assets/voice-1.mp3',
           'narration':'Hello from our team','timing_source':'actual-word',
           'words':[[0,.3,'Hello'],[.4,.8,'from'],[1,1.3,'our'],[1.5,2,'team']]}
    page=motion.inject_layers('<div id="root" data-duration="30"></div>',[scene],30,1080,1920)
    assert 'id="wan-caption-s1-0"' in page
    assert 'data-timing-source="actual-word"' in page
    assert 'Hello from our team' in page and 'data-duration="2"' in page
    assert 'background:transparent' in page
