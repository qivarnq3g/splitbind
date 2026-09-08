import pytest

from splitbind_ref.fingerprint_v2_profile import load_v2_profiles
from splitbind_ref.tile_layout import Tile
from splitbind_ref.tile_layout_v2 import derive_tiles_v2


KEY = bytes.fromhex("00112233445566778899aabbccddeeff" * 2)


@pytest.fixture
def profile():
    return load_v2_profiles()[0]


def test_v2_layout_needs_no_document_nonce(profile):
    first = derive_tiles_v2((2048, 3072), KEY, 0, profile)

    assert first == derive_tiles_v2((2048, 3072), KEY, 0, profile)
    assert first != derive_tiles_v2((2048, 3072), b"w" * 32, 0, profile)
    assert first != derive_tiles_v2((2048, 3072), KEY, 1, profile)
    assert first != derive_tiles_v2((2048, 3072), KEY, 0, load_v2_profiles()[1])


def test_v2_layout_returns_unique_in_bounds_tiles(profile):
    page_shape = (2048, 3072)
    tiles = derive_tiles_v2(page_shape, KEY, 0, profile)

    assert len(tiles) == profile.tiles_per_page
    assert len(set(tiles)) == profile.tiles_per_page
    for tile in tiles:
        assert isinstance(tile, Tile)
        assert 0 <= tile.x < page_shape[1]
        assert 0 <= tile.y < page_shape[0]
        assert tile.x + tile.width <= page_shape[1]
        assert tile.y + tile.height <= page_shape[0]
        assert tile.width == tile.height == profile.tile_size_px


@pytest.mark.parametrize(
    ("page_shape", "key", "page_index", "message"),
    [
        ((0, 3072), KEY, 0, "page"),
        ((2048, 3072), b"", 0, "key"),
        ((2048, 3072), KEY, -1, "page_index"),
        ((6_325, 6_325), KEY, 0, "40"),
    ],
)
def test_v2_layout_rejects_invalid_inputs_before_materializing_tiles(
    profile, page_shape, key, page_index, message
):
    with pytest.raises(ValueError, match=message):
        derive_tiles_v2(page_shape, key, page_index, profile)
