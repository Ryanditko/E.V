"""Tests for Spotify link parsing (embed player)."""
from ev.providers import spotify as sp


def test_parse_links():
    assert sp.parse("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=x") == ("playlist", "37i9dQZF1DXcBWIGoYBM5M")
    assert sp.parse("spotify:track:11dFghVXANMlKmJXsNCbNl") == ("track", "11dFghVXANMlKmJXsNCbNl")
    assert sp.parse("https://open.spotify.com/intl-pt/album/1DFixLWuPkv3KT3TnV35m3") == ("album", "1DFixLWuPkv3KT3TnV35m3")
    assert sp.parse("https://open.spotify.com/user/spotify") is None  # profile has no player
    assert sp.parse("nope") is None


def test_embed_url():
    assert sp.embed_url("playlist", "ABC") == "https://open.spotify.com/embed/playlist/ABC"
