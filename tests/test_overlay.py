"""Qt-drawn labels, sphere meshes and gradient colors, with real Qt/VTK/pyvista."""

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyvista")
np = pytest.importorskip("numpy")

from homa_analyzer import overlay
from homa_analyzer.settings import default_settings


def _ink(pixels):
    return int((pixels[..., 3] > 0).sum())


def test_label_pixels_are_rgba_bottom_up(qapp):
    s = default_settings()
    pixels = overlay.render_label("0.968", "#ff0000", s)
    h, w, c = pixels.shape
    assert c == 4 and w > h > 0
    painted = pixels[pixels[..., 3] > 200]
    assert len(painted) and (painted[:, 0] > 200).all() and (painted[:, 2] < 60).all()
    assert pixels[0, 0, 3] == 0  # transparent background


def test_bigger_font_gives_a_bigger_image(qapp):
    s = default_settings()
    small = overlay.render_label("0.97", "#000000", dict(s, font_size=10))
    big = overlay.render_label("0.97", "#000000", dict(s, font_size=30))
    assert big.shape[0] > small.shape[0] and big.shape[1] > small.shape[1]
    hidpi = overlay.render_label("0.97", "#000000", dict(s, font_size=10), scale=2.0)
    assert hidpi.shape[0] > small.shape[0]


def test_underline_adds_ink_and_italic_widens(qapp):
    s = dict(default_settings(), bold=False)
    plain = overlay.render_label("0.968", "#000000", s)
    under = overlay.render_label("0.968", "#000000", dict(s, underline=True))
    italic = overlay.render_label("0.968", "#000000", dict(s, italic=True))
    assert _ink(under) > _ink(plain)
    assert italic.shape[1] > plain.shape[1]
    assert overlay.label_font(dict(s, bold=True)).bold()


def test_label_actor_is_centered_on_the_world_point(qapp):
    pixels = overlay.render_label("1.000", "#000000", default_settings())
    actor = overlay.label_actor((1.0, 2.0, 3.0), pixels)
    coord = actor.GetPositionCoordinate()
    h, w = pixels.shape[:2]
    assert coord.GetValue()[:2] == pytest.approx((-w / 2, -h / 2))
    assert coord.GetReferenceCoordinate().GetValue() == pytest.approx((1, 2, 3))
    assert not actor.GetPickable()


def test_value_color_spans_the_colormap_and_clips():
    s = dict(default_settings(), colormap="viridis", range_min=0.0, range_max=1.0)
    lo, hi = overlay.value_color(0.0, s), overlay.value_color(1.0, s)
    assert lo != hi
    assert overlay.value_color(-5.0, s) == lo and overlay.value_color(9.0, s) == hi
    assert lo == "#440154"  # viridis' first color


def test_reversed_colormap_swaps_ends():
    s = dict(default_settings(), colormap="coolwarm")
    r = dict(s, colormap="coolwarm_r")
    assert overlay.value_color(0.0, s) == overlay.value_color(1.0, r)


def test_sphere_mesh_carries_values():
    mesh = overlay.sphere_mesh([(0, 0, 0), (5, 0, 0)], 0.5, [0.2, 0.9])
    assert set(np.round(mesh.point_data["HOMA"], 6)) == {0.2, 0.9}
    assert mesh.bounds[1] == pytest.approx(5.5, abs=0.01)
    plain = overlay.sphere_mesh([(0, 0, 0)], 0.3)
    assert "HOMA" not in plain.point_data


def test_legend_mesh_and_args():
    s = dict(default_settings(), range_min=-0.5, range_max=1.0, decimals=2)
    mesh = overlay.legend_mesh((1, 1, 1), s)
    assert list(mesh.point_data["HOMA"]) == [-0.5, 1.0]
    args = overlay.legend_args(s)
    assert args["title"] == "HOMA" and args["fmt"] == "%.2f" and args["vertical"]
    flat = overlay.legend_args(dict(s, legend_vertical=False))
    assert flat["width"] > flat["height"]


def test_ring_outline_closes_the_loop():
    square = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    mesh = overlay.ring_outline([square], radius=0.1)
    xmin, xmax, ymin, ymax, *_ = mesh.bounds
    # Closed and symmetric: every side is tubed, including the last one back.
    assert xmin == pytest.approx(ymin) == pytest.approx(-0.1, abs=0.01)
    assert xmax == pytest.approx(ymax) and xmax > 1.05
    two = overlay.ring_outline([square, [(5 + x, y, z) for x, y, z in square]])
    assert two.bounds[1] > 5.9
