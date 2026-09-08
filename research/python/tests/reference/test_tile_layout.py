import pytest

from splitbind_ref.tile_layout import Tile, derive_tiles


PROFILE = {"schema_version": 1, "tile_size_px": 256, "tiles_per_page": 12}
PAGE_SHAPE = (1024, 1280)
KEY = bytes.fromhex("00112233445566778899aabbccddeeff" * 2)
NONCE = bytes.fromhex("fedcba98765432100123456789abcdef")


def test_tile_layout_is_reproducible_and_bound_to_every_seed_input():
    expected = derive_tiles(PAGE_SHAPE, KEY, NONCE, 3, PROFILE)

    assert derive_tiles(PAGE_SHAPE, KEY, NONCE, 3, PROFILE) == expected
    assert derive_tiles(PAGE_SHAPE, bytes(32), NONCE, 3, PROFILE) != expected
    assert derive_tiles(PAGE_SHAPE, KEY, bytes(16), 3, PROFILE) != expected
    assert derive_tiles(PAGE_SHAPE, KEY, NONCE, 4, PROFILE) != expected


def test_tile_layout_returns_requested_non_overlapping_in_bounds_tiles():
    tiles = derive_tiles(PAGE_SHAPE, KEY, NONCE, 3, PROFILE)

    assert len(tiles) == 12
    assert len(set(tiles)) == 12
    for tile in tiles:
        assert 0 <= tile.x < PAGE_SHAPE[1]
        assert 0 <= tile.y < PAGE_SHAPE[0]
        assert tile.x + tile.width <= PAGE_SHAPE[1]
        assert tile.y + tile.height <= PAGE_SHAPE[0]
        assert tile.width == tile.height == 256
    for index, left in enumerate(tiles):
        for right in tiles[index + 1 :]:
            assert (
                left.x + left.width <= right.x
                or right.x + right.width <= left.x
                or left.y + left.height <= right.y
                or right.y + right.height <= left.y
            )


def test_tile_layout_has_a_stable_keyed_permutation_golden_vector():
    tiles = derive_tiles(PAGE_SHAPE, KEY, NONCE, 3, PROFILE)

    assert tiles == (
        Tile(x=256, y=0, width=256, height=256),
        Tile(x=768, y=768, width=256, height=256),
        Tile(x=768, y=512, width=256, height=256),
        Tile(x=768, y=0, width=256, height=256),
        Tile(x=1024, y=0, width=256, height=256),
        Tile(x=1024, y=768, width=256, height=256),
        Tile(x=1024, y=512, width=256, height=256),
        Tile(x=1024, y=256, width=256, height=256),
        Tile(x=0, y=768, width=256, height=256),
        Tile(x=256, y=256, width=256, height=256),
        Tile(x=0, y=512, width=256, height=256),
        Tile(x=0, y=256, width=256, height=256),
    )


@pytest.mark.parametrize(
    ("page_shape", "key", "nonce", "page_index", "profile", "message"),
    [
        ((255, 1024), KEY, NONCE, 0, PROFILE, "page"),
        (PAGE_SHAPE, b"", NONCE, 0, PROFILE, "key"),
        (PAGE_SHAPE, KEY, b"", 0, PROFILE, "nonce"),
        (PAGE_SHAPE, KEY, NONCE, -1, PROFILE, "page_index"),
        (PAGE_SHAPE, KEY, NONCE, 0, {**PROFILE, "tile_size_px": 128}, "tile_size_px"),
    ],
)
def test_tile_layout_rejects_invalid_or_uncontracted_inputs(
    page_shape, key, nonce, page_index, profile, message
):
    with pytest.raises(ValueError, match=message):
        derive_tiles(page_shape, key, nonce, page_index, profile)
