"""Policy gates are tested without database or paid provider access."""
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

from semasa.video_format_policy import normalize, prepare_brand


@pytest.mark.parametrize('row', [{'voice':'clone'},{'options':{'talking_avatar':True}},
                                  {'options':{'source_footage':'u/source.mp4'}}])
def test_unconfigured_capability_is_not_silently_generated(row):
    with pytest.raises(ValueError,match='unconfigured|unsupported'):
        normalize(row)


def test_explicit_off_wins_over_stale_voiced_format():
    row = normalize({'voice':'off','options':{'format':'english-voiced'}})
    assert row['voice'] == 'off'
    assert row['options']['format'] == 'silent-first'


def test_manual_voice_and_gender_override_survive():
    assert normalize({'language':'en','voice':'female'})['voice'] == 'female'
    assert normalize({'language':'en','voice':'en-GB-RyanNeural'})['voice'] == 'en-GB-RyanNeural'
    assert normalize({'language':'en','voice':'kitten'})['voice'] == 'kitten'


def test_missing_or_foreign_personal_avatar_blocks(tmp_path):
    with pytest.raises(ValueError,match='avatar'):
        prepare_brand(None,{'stream':'linkedin'},tmp_path)
    row = {'stream':'linkedin','created_by':'owner','options':{'personal_avatar':{
        'path':'other/avatar.png','mime':'image/png','size':100,'rights':'self-owned'}}}
    with pytest.raises(ValueError,match='creator-owned'):
        prepare_brand(None,row,tmp_path)


def test_owned_decodable_still_prepares_without_personal_media_in_repo(tmp_path):
    buff = BytesIO()
    Image.new('RGB',(8,8),'green').save(buff,format='PNG')
    data = buff.getvalue()
    ref = {'path':'owner/avatar.png','mime':'image/png','size':len(data),'rights':'self-owned'}
    store = SimpleNamespace(storage=SimpleNamespace(from_=lambda _:SimpleNamespace(download=lambda _:data)))
    brand = prepare_brand(store,{'stream':'linkedin','created_by':'owner','options':{'personal_avatar':ref}},tmp_path)
    assert brand['profile'] == 'linkedin-personal'
    assert Image.open(tmp_path / brand['avatar']).size == (8,8)
